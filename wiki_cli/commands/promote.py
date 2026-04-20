"""wiki promote command - review and promote compiled drafts into wiki.

v0.2.0: Supports audit flow with compiled/ staging area.
- Without arguments: list pending compiled drafts sorted by reference frequency
- With a file: promote that compiled draft to wiki/
- --reject --reason: reject and feed back to compile_feedback.md
"""
import json
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from ..core.compiler import (
    _atomic_write,
    _update_index,
    _write_journal,
    _parse_llm_response,
    _apply_actions,
    _get_index_content as _get_compile_index_content,
    _get_schema_content as _get_compile_schema_content,
)
from ..core.config import Config
from ..core.llm import LLMClient
from ..core.state import WikiState
from ..prompts.ingest import INGEST_SYSTEM, build_ingest_prompt

console = Console()


# Tag-to-category mapping for wiki subdirectory placement
_TAG_CATEGORIES = {
    "concept": "concepts",
    "design-philosophy": "concepts",
    "methodology": "concepts",
    "principle": "concepts",
    "topic": "topics",
    "technology": "topics",
    "ai": "topics",
    "llm": "topics",
    "engineering": "topics",
    "knowledge-management": "meta",
    "system-design": "meta",
    "tool": "meta",
}


def _infer_category(first_tag: str) -> str:
    """Infer wiki subdirectory from the first tag."""
    if not first_tag:
        return "concepts"
    tag_lower = first_tag.lower().replace("_", "-")
    return _TAG_CATEGORIES.get(tag_lower, "concepts")


def promote_command(
    config: Config,
    output_file: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    promote_all: bool = False,
    reject: str | None = None,
    reason: str | None = None,
):
    """Promote compiled drafts or output Q&A into wiki entries."""

    # Mode 1: Reject a compiled file
    if reject:
        _handle_reject(config, reject, reason or "未说明原因")
        return

    # Mode 2: List pending compiled drafts
    if output_file is None and not promote_all:
        _list_pending(config)
        return

    # Mode 3: Promote all pending
    if promote_all:
        _promote_all_pending(config, dry_run=dry_run, yes=yes)
        return

    # Mode 4: Promote a specific file
    # Try compiled/ first, then outputs/ (backward compat)
    path = _resolve_path(output_file, config)
    if path.is_relative_to(config.compiled_dir) if config.compiled_dir.exists() else False:
        _promote_compiled(config, path, dry_run=dry_run, yes=yes)
    else:
        # Legacy: promote from outputs/
        _promote_legacy_output(config, path, dry_run=dry_run, yes=yes)


def _list_pending(config: Config):
    """List pending compiled drafts sorted by reference frequency."""
    # Always scan compiled/ directory for actual .md files
    # (state tracking may have directory-level paths that don't match individual files)
    pending_files = _scan_compiled_dir(config)

    if not pending_files:
        console.print("[dim]No pending compiled drafts.[/dim]")
        return

    # Calculate reference frequency for sorting
    wiki_content = _get_all_wiki_content(config)
    scored = []
    for entry in pending_files:
        path_str = entry["path"]
        compiled_path = config.wiki_root / path_str
        if not compiled_path.exists():
            continue

        # Read compiled file to get title/tags for frequency count
        try:
            content = compiled_path.read_text(encoding="utf-8")[:2000]
        except Exception:
            content = ""

        # Extract title and tags from frontmatter
        title = _extract_frontmatter_value(content, "title") or compiled_path.stem
        tags_str = _extract_frontmatter_value(content, "tags") or ""
        tags = [t.strip().strip('"').strip("'") for t in tags_str.strip("[]").split(",") if t.strip()]

        # Count references in wiki
        freq = _count_references(wiki_content, title, tags, compiled_path.stem)

        # Get compiled_at from frontmatter or state
        compiled_date = _extract_frontmatter_value(content, "compiled_date") or ""

        scored.append({
            "path": path_str,
            "title": title,
            "freq": freq,
            "compiled_at": compiled_date,
        })

    # Sort by frequency (descending)
    scored.sort(key=lambda x: x["freq"], reverse=True)

    # Display
    table = Table(title="Pending Compiled Drafts", show_header=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", style="cyan")
    table.add_column("Refs", justify="right")
    table.add_column("Path", style="dim")
    table.add_column("Compiled", style="dim")

    for i, item in enumerate(scored, 1):
        compiled_date = item["compiled_at"][:10] if item["compiled_at"] else "—"
        table.add_row(
            str(i),
            item["title"],
            str(item["freq"]),
            item["path"],
            compiled_date,
        )

    console.print(table)
    console.print("\nTo promote: [cyan]wiki promote <path>[/cyan]")
    console.print("To reject:  [cyan]wiki promote --reject <path> --reason \"原因\"[/cyan]")
    console.print("To promote all: [cyan]wiki promote --all[/cyan]")


def _apply_patch(config: Config, patch_file: Path):
    """Apply a patch (section append) to an existing wiki page."""
    try:
        patch = json.loads(patch_file.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"  [yellow]⊘ Skipping invalid patch[/yellow] {patch_file.name}: {e}")
        return

    if patch.get("type") != "update":
        return

    target_path = patch.get("path", "")
    section = patch.get("section", "")
    append_text = patch.get("append", "")

    if not target_path or not section or not append_text:
        return

    # Resolve target wiki file
    wiki_file = config.wiki_root / target_path
    if not wiki_file.exists():
        console.print(f"  [yellow]⊘ Patch target not found[/yellow] {target_path}")
        return

    content = wiki_file.read_text(encoding="utf-8")

    # Find the section header and append after its content block
    section_pattern = re.escape(section)
    match = re.search(rf'^{section_pattern}\s*$', content, re.MULTILINE)
    if not match:
        console.print(f"  [yellow]⊘ Section not found[/yellow] {section} in {target_path}")
        return

    # Find the next section header (## or ---) after this one
    after_match = content[match.end():]
    next_section = re.search(r'^#{1,3}\s|^---', after_match, re.MULTILINE)

    if next_section:
        insert_pos = match.end() + next_section.start()
        new_content = content[:insert_pos] + f"\n{append_text}\n" + content[insert_pos:]
    else:
        new_content = content + f"\n{append_text}\n"

    _atomic_write(wiki_file, new_content)
    console.print(f"  [blue]✓ patched[/blue] {target_path} ({section})")


def _promote_compiled(config: Config, compiled_path: Path, dry_run: bool = False, yes: bool = False):
    """Promote a compiled draft file directly to wiki/.

    The compile stage already did the LLM structuring. Promote simply moves
    the file from compiled/ to wiki/, updates frontmatter, and regenerates index.
    No second LLM call needed — that would violate harness principle
    (层次正确性: promote层只做搬运和确认，不做再编译).
    """
    if not compiled_path.exists():
        console.print(f"[red]✗ File not found:[/red] {compiled_path}")
        return

    content = compiled_path.read_text(encoding="utf-8")
    console.print(f"\n[bold]Promoting:[/bold] {compiled_path.relative_to(config.wiki_root)}\n")
    console.print(Panel(Markdown(content[:2000]), title="Draft Content", border_style="dim"))

    if dry_run:
        console.print("\n[yellow]--dry-run: no files written.[/yellow]")
        return

    if not yes:
        console.print()
        confirmed = click.confirm("Promote this draft to wiki?", default=False)
        if not confirmed:
            console.print("[dim]Aborted. Nothing written.[/dim]")
            return

    state = WikiState(config)

    # Determine wiki destination path
    # Use tags to infer subdirectory, default to wiki/concepts/
    tags_match = re.search(r'^tags:\s*\[(.+?)\]', content, re.MULTILINE)
    first_tag = ""
    if tags_match:
        tags_str = tags_match.group(1)
        first_tag = [t.strip().strip('"').strip("'") for t in tags_str.split(",")][0] if tags_str else ""

    # Simple category mapping based on first tag
    category_dir = _infer_category(first_tag)
    dest_dir = config.wiki_dir / category_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / compiled_path.name

    # Update frontmatter: remove pending_audit status
    promoted_content = content.replace('status: "pending_audit"', 'status: "promoted"')
    # Remove compiled-specific fields
    promoted_content = re.sub(r'^raw_source:.*\n', '', promoted_content, flags=re.MULTILINE)
    promoted_content = re.sub(r'^compiled_date:.*\n', '', promoted_content, flags=re.MULTILINE)

    # Write to wiki/
    _atomic_write(dest_path, promoted_content)
    console.print(f"  [green]✓ promoted to[/green] {dest_path.relative_to(config.wiki_root)}")

    # Update index
    _update_index(config)

    # Write journal
    today = date.today().isoformat()
    summary = f"Promoted {compiled_path.name} to wiki/{category_dir}/"
    _write_journal(config, compiled_path.name, f"Promoted from compiled/ to wiki/{category_dir}/", summary)

    # Mark as promoted in state
    rel_path = str(compiled_path.relative_to(config.wiki_root))
    state.mark_promoted(rel_path)

    # Remove compiled file
    compiled_path.unlink()

    # Apply any associated patch files (updates to existing wiki pages)
    # Patches are named patch-<stem>.json or patch-<raw-source>.json
    for patch_file in compiled_path.parent.glob("patch-*.json"):
        _apply_patch(config, patch_file)
        patch_file.unlink()

    console.print(f"\n[green]✓ Promoted.[/green] {dest_path.relative_to(config.wiki_root)}")


def _apply_patches_for_entry(config: Config, state: WikiState, path_str: str, compiled_path: Path, dry_run: bool = False) -> bool:
    """Apply patch files for a patch-only compiled entry (no .md file on disk).

    When compile produces only updates (no new pages), there's no .md file
    in compiled/, only patch-*.json files. This function applies those patches
    and marks the entry as promoted.
    """
    # Derive stem from path (may or may not have .md extension)
    stem = compiled_path.stem if compiled_path.suffix else compiled_path.name
    parent = compiled_path.parent
    if not parent.exists():
        return False

    # Find patch files matching this entry's stem
    patch_files = [
        f for f in parent.glob("patch-*.json")
        if stem in f.stem
    ]
    if not patch_files:
        return False

    console.print(f"  [dim]Patch-only entry:[/dim] {path_str}")
    if dry_run:
        console.print(f"  [yellow]--dry-run: would apply {len(patch_files)} patch(es)[/yellow]")
        return True

    for patch_file in patch_files:
        _apply_patch(config, patch_file)
        patch_file.unlink()

    state.mark_promoted(path_str)
    console.print(f"  [green]✓ patches applied[/green] ({len(patch_files)})")
    return True


def _promote_all_pending(config: Config, dry_run: bool = False, yes: bool = False):
    """Promote all pending compiled drafts."""
    state = WikiState(config)
    pending = state.get_pending_compiled()

    if not pending:
        console.print("[dim]No pending compiled drafts to promote.[/dim]")
        return

    console.print(f"[bold]{len(pending)} pending draft(s) to promote.[/bold]")

    if not yes and not dry_run:
        confirmed = click.confirm(f"Promote all {len(pending)} drafts?", default=False)
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            return

    promoted = 0
    errors = []
    for entry in pending:
        path_str = entry.get("path", "")
        compiled_path = config.wiki_root / path_str
        if not compiled_path.exists():
            # Patch-only entry: no .md file, but may have patch .json files
            # to apply to existing wiki pages
            patch_applied = _apply_patches_for_entry(config, state, path_str, compiled_path, dry_run)
            if patch_applied:
                promoted += 1
            continue
        try:
            if not dry_run:
                _promote_compiled(config, compiled_path, dry_run=False, yes=True)
            promoted += 1
        except Exception as e:
            errors.append((path_str, str(e)))

    if dry_run:
        console.print(f"\n[yellow]--dry-run: would promote {promoted} draft(s).[/yellow]")
    else:
        console.print(f"\n[bold green]Done.[/bold green] {promoted} promoted, {len(errors)} errors.")


def _handle_reject(config: Config, reject_path: str, reason: str):
    """Reject a compiled draft and write feedback to compile_feedback.md."""
    # Resolve the path
    compiled_path = Path(reject_path).expanduser()
    if not compiled_path.exists():
        candidate = config.wiki_root / reject_path
        if candidate.exists():
            compiled_path = candidate
        else:
            console.print(f"[red]✗ File not found:[/red] {reject_path}")
            return

    if not compiled_path.is_relative_to(config.compiled_dir) and config.compiled_dir.exists():
        # Also check if it's under compiled/
        candidate = config.compiled_dir / reject_path
        if candidate.exists():
            compiled_path = candidate

    # Write feedback to compile_feedback.md
    _append_rejection_feedback(config, compiled_path, reason)

    # Mark as rejected in state
    state = WikiState(config)
    rel_path = str(compiled_path.relative_to(config.wiki_root))
    state.mark_rejected(rel_path, reason)

    # Delete the compiled file and all associated patches
    if compiled_path.exists():
        compiled_path.unlink()
    # Clean up all patch files in the same directory
    if compiled_path.parent.exists():
        for patch_file in compiled_path.parent.glob("patch-*.json"):
            patch_file.unlink()

    console.print(f"[yellow]✗ Rejected[/yellow] {compiled_path.name}")
    console.print(f"  Reason: {reason}")
    console.print(f"  Feedback written to compile_feedback.md")


def _append_rejection_feedback(config: Config, compiled_path: Path, reason: str):
    """Append rejection reason to compile_feedback.md."""
    today = date.today().isoformat()
    rel_path = str(compiled_path.relative_to(config.wiki_root))

    feedback_path = config.compile_feedback_file
    if feedback_path.exists():
        existing = feedback_path.read_text(encoding="utf-8")
    else:
        existing = (
            "# Compile 反馈记录\n"
            "# 此文件由 wiki promote --reject 自动追加，供 Compile 阶段参考\n"
        )

    entry = f"\n\n## {today} — {rel_path}\n- 原因：{reason}\n"
    _atomic_write(feedback_path, existing + entry)


def _show_plan(result: dict):
    """Display the LLM's proposed changes for human review."""
    console.print(Rule("Proposed Wiki Changes"))
    console.print(f"[bold]Summary:[/bold] {result.get('summary', '—')}\n")

    actions = result.get("actions", [])
    if not actions:
        console.print("[dim]No wiki pages would be created or updated.[/dim]")
        return

    for i, action in enumerate(actions, 1):
        action_type = action.get("type", "?")
        path = action.get("path", "?")
        color = "green" if action_type == "create" else "blue"
        label = "NEW" if action_type == "create" else "UPDATE"

        console.print(f"[{color}][{label}][/{color}] {path}")

        if action_type == "create":
            content_preview = action.get("content", "")[:400]
            console.print(Panel(content_preview + ("..." if len(action.get("content", "")) > 400 else ""),
                                border_style="dim", padding=(0, 1)))
        elif action_type == "update":
            section = action.get("section", "")
            append_preview = action.get("append", "")[:300]
            console.print(f"  [dim]section:[/dim] {section}")
            console.print(Panel(append_preview + ("..." if len(action.get("append", "")) > 300 else ""),
                                border_style="dim", padding=(0, 1)))
    console.print(Rule())


def _resolve_path(file_ref: str, config: Config) -> Path:
    """Resolve a file reference to an actual path."""
    p = Path(file_ref).expanduser()
    if p.exists():
        return p

    # Try under compiled/
    candidate = config.wiki_root / file_ref
    if candidate.exists():
        return candidate

    candidate = config.compiled_dir / file_ref
    if candidate.exists():
        return candidate

    # Try under outputs/ (legacy)
    candidate = config.outputs_dir / file_ref
    if candidate.exists():
        return candidate

    # Fuzzy match in compiled/
    if config.compiled_dir.exists():
        matches = list(config.compiled_dir.rglob(f"*{file_ref}*"))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            console.print("Multiple matches in compiled/:")
            for m in matches:
                console.print(f"  {m.relative_to(config.wiki_root)}")
            raise click.ClickException("Specify a more exact name.")

    # Fuzzy match in outputs/
    if config.outputs_dir.exists():
        matches = list(config.outputs_dir.glob(f"*{file_ref}*"))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            console.print("Multiple matches in outputs/:")
            for m in matches:
                console.print(f"  {m.name}")
            raise click.ClickException("Specify a more exact name.")

    raise click.ClickException(f"File not found: {file_ref}")


def _scan_compiled_dir(config: Config) -> list[dict]:
    """Scan compiled/ directory for pending files not yet in state."""
    if not config.compiled_dir.exists():
        return []

    results = []
    for f in config.compiled_dir.rglob("*.md"):
        if f.name.startswith("patch-"):
            continue
        rel = str(f.relative_to(config.wiki_root))
        results.append({"path": rel, "compiled_at": "", "status": "pending"})
    return results


def _get_all_wiki_content(config: Config) -> str:
    """Get concatenated wiki content for reference counting."""
    if not config.wiki_dir.exists():
        return ""
    parts = []
    for f in config.wiki_dir.rglob("*.md"):
        if f.name == "index.md" or f.parent.name == "journal":
            continue
        try:
            parts.append(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return "\n".join(parts)


def _count_references(wiki_content: str, title: str, tags: list[str], stem: str) -> int:
    """Count how many times a title/tags/stem are referenced in wiki content."""
    count = 0
    for term in [stem, title] + tags:
        if term and len(term) > 2:
            count += len(re.findall(re.escape(term), wiki_content, re.IGNORECASE))
    return count


def _extract_frontmatter_value(content: str, key: str) -> str | None:
    """Extract a value from YAML frontmatter text."""
    match = re.search(rf"^{key}:\s*(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"').strip("'")
    return None


def _mark_promoted(path: Path):
    """Mark a file as promoted (legacy for outputs/)."""
    try:
        content = path.read_text(encoding="utf-8")
        content = content.replace("promoted_to_wiki: false", "promoted_to_wiki: true")
        path.write_text(content, encoding="utf-8")
    except Exception:
        pass


def _get_index_content(config: Config) -> str:
    """Read wiki index.md for legacy promote."""
    try:
        return _get_compile_index_content(config)
    except Exception:
        return ""


def _get_schema_content(config: Config) -> str:
    """Read schema.md for legacy promote."""
    try:
        return _get_compile_schema_content(config)
    except Exception:
        return ""


def _promote_legacy_output(config: Config, path: Path, dry_run: bool = False, yes: bool = False):
    """Promote from outputs/ (v0.1.0 backward compatibility)."""
    console.print(f"\n[bold]Promoting:[/bold] {path.name}\n")

    content = path.read_text(encoding="utf-8")
    console.print(Panel(Markdown(content[:2000]), title="Content to promote", border_style="dim"))

    console.print("\n[dim]Asking LLM to plan wiki changes...[/dim]")
    state = WikiState(config)
    llm = LLMClient(config)

    raw_content = content
    index_content = _get_index_content(config)
    schema_content = _get_schema_content(config)

    prompt = build_ingest_prompt(
        raw_content=raw_content,
        raw_filename=path.name,
        existing_index=index_content,
        schema_content=schema_content,
    )

    response = llm.complete(INGEST_SYSTEM, prompt)

    try:
        result = _parse_llm_response(response)
    except Exception as e:
        console.print(f"[red]✗ LLM response parse error:[/red] {e}")
        return

    _show_plan(result)

    if dry_run:
        console.print("\n[yellow]--dry-run: no files written.[/yellow]")
        return

    if not yes:
        console.print()
        confirmed = click.confirm("Apply these changes to your wiki?", default=False)
        if not confirmed:
            console.print("[dim]Aborted. Nothing written.[/dim]")
            return

    # Apply
    temp_raw = config.raw_dir / "misc" / f"promoted-{path.name}"
    temp_raw.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, temp_raw)

    try:
        actions = result.get("actions", [])
        summary = result.get("summary", "（promoted from outputs）")
        journal_entry = result.get("journal_entry", "")

        affected = _apply_actions(actions, config)
        _update_index(config)
        _write_journal(config, path.name, journal_entry, summary)
        state.mark_processed(temp_raw, affected)
    finally:
        if temp_raw.exists():
            temp_raw.unlink()

    _mark_promoted(path)
    console.print(f"\n[green]✓ Promoted.[/green] {len(affected)} wiki page(s) affected.")
    for p in affected:
        console.print(f"  {p}")
