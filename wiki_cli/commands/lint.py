"""wiki lint command - health check for the knowledge base.

--auto mode scope (intentionally narrow to avoid surprises):
  WILL auto-fix:
    - wiki/index.md regeneration (pure derived file, safe to overwrite)
  WILL NOT auto-fix:
    - Wiki entry content (requires human review)
    - Broken wikilinks inside pages (use --fix-links to fix)
    - Orphan pages (marking only, not deleting)
    - schema.md (human-owned, never touched by tool)
    - Raw files

--fix-links mode:
  WILL auto-fix:
    - Broken [[wikilinks]] via fuzzy matching to valid stems
    - Unresolvable links escaped as plain text
  Uses the same fuzzy matching as compile-time link fixing.
"""
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ..core.config import Config
from ..core.llm import LLMClient
from ..core.state import WikiState
from ..prompts.lint import LINT_SYSTEM, build_lint_prompt
from ..utils.markdown import find_broken_links, find_orphan_pages, get_valid_stems, fix_wikilinks_in_content

console = Console()


def _build_wiki_summary(wiki_dir: Path) -> str:
    """Build a summary of all wiki files (paths + frontmatter) for LLM."""
    if not wiki_dir.exists():
        return "（wiki 目录不存在）"

    lines = []
    for md_file in sorted(wiki_dir.rglob("*.md")):
        if md_file.name == "index.md":
            continue
        rel = md_file.relative_to(wiki_dir)
        try:
            content = md_file.read_text(encoding="utf-8")
            # Extract frontmatter block
            fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            fm_str = fm_match.group(1)[:200] if fm_match else "(no frontmatter)"
            lines.append(f"### {rel}\n```yaml\n{fm_str}\n```")
        except Exception:
            lines.append(f"### {rel}\n(unreadable)")

    return "\n\n".join(lines) if lines else "（无 wiki 条目）"


def lint_command(config: Config, auto: bool = False, fix_links: bool = False):
    """Run health check on the knowledge base."""
    state = WikiState(config)

    if not config.wiki_dir.exists():
        console.print("[red]Wiki directory not found.[/red] Run `wiki init` first.")
        return

    # Fast local checks (no LLM)
    console.print("[dim]Running local checks...[/dim]")

    broken = find_broken_links(config.wiki_dir)
    orphans = find_orphan_pages(config.wiki_dir)

    # Count stale pages
    stale_days = config.get("behavior.lint_stale_days", 30)
    stale_pages = _find_stale_pages(config.wiki_dir, stale_days)

    # Count unprocessed raw files
    unprocessed = state.get_unprocessed_files(batch_size=9999)

    # Count contradiction markers
    contradictions = _count_markers(config.wiki_dir, r"⚠️ 矛盾标注")

    # Fix broken links if requested
    if fix_links and broken:
        _fix_broken_links(config, broken)

    # Display quick summary
    _display_quick_report(broken, orphans, stale_pages, unprocessed, contradictions)

    # LLM-powered deep lint
    if click.confirm("\nRun deep LLM health check?", default=not auto):
        _run_llm_lint(config, state, stale_days, auto)

    state.update_last_lint()


def _fix_broken_links(config: Config, broken: list[tuple[Path, str]]):
    """Fix broken wikilinks in all wiki pages using fuzzy matching."""
    valid_stems = get_valid_stems(config.wiki_dir)
    fixed_count = 0
    escaped_count = 0

    # Group by file for batch processing
    files_with_broken: dict[Path, set[str]] = {}
    for file_path, link in broken:
        files_with_broken.setdefault(file_path, set()).add(link)

    for file_path, broken_links in files_with_broken.items():
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            continue

        fixed_content, fixes = fix_wikilinks_in_content(content, valid_stems)
        if fixes:
            from ..core.compiler import _atomic_write
            _atomic_write(file_path, fixed_content)
            for fix_desc in fixes:
                if "→ `" in fix_desc:
                    escaped_count += 1
                else:
                    fixed_count += 1
                console.print(f"  [yellow]⟳[/yellow] {file_path.name}: {fix_desc}")

    console.print(f"\n[green]✓ Link fix complete:[/green] {fixed_count} fixed, {escaped_count} escaped (no match)")


def _display_quick_report(broken, orphans, stale_pages, unprocessed, contradictions):
    table = Table(title="Quick Health Check", show_header=True)
    table.add_column("Check", style="cyan")
    table.add_column("Count")
    table.add_column("Status")

    def status(count, warn_threshold=0):
        if count == 0:
            return "[green]✓ OK[/green]"
        elif count <= warn_threshold:
            return f"[yellow]⚠ {count}[/yellow]"
        return f"[red]✗ {count}[/red]"

    table.add_row("Broken links", str(len(broken)), status(len(broken)))
    table.add_row("Orphan pages", str(len(orphans)), status(len(orphans), 5))
    table.add_row("Stale pages", str(len(stale_pages)), status(len(stale_pages), 10))
    table.add_row("Unprocessed raw files", str(len(unprocessed)), status(len(unprocessed), 3))
    table.add_row("Unresolved contradictions", str(contradictions), status(contradictions))

    console.print(table)

    if broken:
        console.print("\n[red]Broken links:[/red]")
        for file, link in broken[:10]:
            console.print(f"  {file.name}: [[{link}]]")

    if orphans:
        console.print("\n[yellow]Orphan pages:[/yellow]")
        for p in orphans[:10]:
            console.print(f"  {p.name}")


def _run_llm_lint(config: Config, state: WikiState, stale_days: int, auto: bool):
    """Deep LLM-powered lint."""
    llm = LLMClient(config)

    wiki_summary = _build_wiki_summary(config.wiki_dir)
    index_content = ""
    index_path = config.wiki_dir / "index.md"
    if index_path.exists():
        index_content = index_path.read_text(encoding="utf-8")[:5000]

    schema_content = ""
    if config.schema_file.exists():
        schema_content = config.schema_file.read_text(encoding="utf-8")[:2000]

    prompt = build_lint_prompt(
        wiki_files_summary=wiki_summary[:20000],
        index_content=index_content,
        schema_content=schema_content,
        stale_days=stale_days,
    )

    console.print("\n[dim]Running LLM analysis...[/dim]")
    response = llm.complete(LINT_SYSTEM, prompt, operation="lint")

    # Parse JSON response
    try:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
        else:
            raise ValueError("No JSON in response")
    except Exception as e:
        console.print(f"[yellow]Could not parse LLM response as JSON: {e}[/yellow]")
        console.print(response[:2000])
        return

    # Save lint report
    today = date.today().isoformat()
    journal_dir = config.wiki_dir / "journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    report_path = journal_dir / f"lint-{today}.md"

    report_lines = [
        f"# Lint Report {today}\n\n",
        f"**Summary**: {result.get('summary', '')}\n\n",
        "## Issues\n\n",
    ]
    for issue in result.get("issues", []):
        severity_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(
            issue.get("severity", "info"), "⚪"
        )
        report_lines.append(
            f"- {severity_icon} **{issue.get('type', '?')}** — "
            f"`{issue.get('path', '')}`: {issue.get('description', '')}\n"
            f"  - Fix: {issue.get('fix', '')}\n"
        )

    stats = result.get("stats", {})
    report_lines.append(f"\n## Stats\n\n{json.dumps(stats, indent=2, ensure_ascii=False)}\n")

    report_content = "".join(report_lines)
    report_path.write_text(report_content, encoding="utf-8")
    console.print(f"\n[green]✓ Report saved to[/green] {report_path.relative_to(config.wiki_root)}")

    # Auto-fix: ONLY index.md regeneration (derived file, safe to overwrite).
    # All other issues require human review - this is intentional.
    # See module docstring for the full auto-fix scope.
    if auto and result.get("index_sync_needed"):
        index_path = config.wiki_dir / "index.md"
        # Prefer our local regeneration over LLM-generated index content
        from ..core.compiler import _update_index
        _update_index(config)
        console.print("[green]✓ index.md regenerated from actual file structure[/green]")
        console.print("[dim]  (Other issues above require manual review)[/dim]")


def _find_stale_pages(wiki_dir: Path, stale_days: int) -> list[Path]:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    stale = []
    for p in wiki_dir.rglob("*.md"):
        if p.name == "index.md":
            continue
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            stale.append(p)
    return stale


def _count_markers(wiki_dir: Path, pattern: str) -> int:
    count = 0
    for p in wiki_dir.rglob("*.md"):
        try:
            content = p.read_text(encoding="utf-8")
            count += len(re.findall(pattern, content))
        except Exception:
            pass
    return count
