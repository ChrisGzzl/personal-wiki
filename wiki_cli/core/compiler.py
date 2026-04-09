"""Core compilation engine - the heart of wiki ingest."""
import json
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import Config
from .llm import LLMClient
from .state import WikiState
from ..prompts.ingest import INGEST_SYSTEM, build_ingest_prompt

console = Console()


class CompileError(Exception):
    pass


def _read_file_safe(path: Path, max_chars: int = 80000) -> str:
    """Read file, truncating if too large."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[... truncated at {max_chars} chars ...]"
        return text
    except Exception as e:
        return f"[Failed to read file: {e}]"


def _get_index_content(config: Config) -> str:
    index_path = config.wiki_dir / "index.md"
    if index_path.exists():
        return _read_file_safe(index_path, 10000)
    return "（知识库为空，尚无条目）"


def _get_schema_content(config: Config) -> str:
    if config.schema_file.exists():
        return _read_file_safe(config.schema_file, 8000)
    return "（无 schema.md，使用默认规则）"


def _get_existing_wiki_stems(config: Config) -> list[str]:
    """Return all existing wiki page stems (filename without .md extension)."""
    if not config.wiki_dir.exists():
        return []
    stems = []
    for p in config.wiki_dir.rglob("*.md"):
        if p.name != "index.md" and p.parent.name != "journal":
            stems.append(p.stem)
    return stems


def _parse_llm_response(response: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Strip ```json ... ``` wrapper if present
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # Try to find raw JSON object
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            raise CompileError("LLM response contains no JSON object")
        json_str = match.group(0)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise CompileError(f"Failed to parse LLM JSON response: {e}")


def _atomic_write(path: Path, content: str):
    """Write content atomically using a temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
    ) as f:
        f.write(content)
        tmp_path = Path(f.name)
    tmp_path.replace(path)


def _apply_actions(actions: list[dict], config: Config) -> list[str]:
    """Apply create/update actions from LLM response. Returns affected paths."""
    affected = []
    today = date.today().isoformat()

    for action in actions:
        action_type = action.get("type")
        rel_path = action.get("path", "")
        if not rel_path:
            continue

        # Ensure path is under wiki_root
        target = config.wiki_root / rel_path
        affected.append(rel_path)

        if action_type == "create":
            content = action.get("content", "")
            if not content:
                continue
            _atomic_write(target, content)
            console.print(f"  [green]✓ created[/green] {rel_path}")

        elif action_type == "update":
            if not target.exists():
                # Create it if doesn't exist
                content = action.get("content", "")
                if content:
                    _atomic_write(target, content)
                    console.print(f"  [green]✓ created[/green] {rel_path}")
                continue

            existing = target.read_text(encoding="utf-8")
            section = action.get("section")
            append_text = action.get("append", "")

            if section and section in existing:
                # Append after the section header
                idx = existing.find(section)
                # Find the next ## heading or end of file
                next_section = re.search(r"\n## ", existing[idx + len(section) :])
                if next_section:
                    insert_pos = idx + len(section) + next_section.start()
                    new_content = (
                        existing[:insert_pos]
                        + f"\n\n{append_text}"
                        + existing[insert_pos:]
                    )
                else:
                    new_content = existing + f"\n\n{append_text}"
            else:
                new_content = existing + f"\n\n{append_text}"

            # Update the 'updated' date in frontmatter
            new_content = re.sub(
                r"^updated:.*$", f"updated: \"{today}\"", new_content, flags=re.MULTILINE
            )
            _atomic_write(target, new_content)
            console.print(f"  [blue]✓ updated[/blue] {rel_path}")

    return affected


def _write_journal(config: Config, raw_filename: str, journal_entry: str, summary: str):
    """Write a journal entry for this compilation."""
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    journal_dir = config.wiki_dir / "journal"
    journal_dir.mkdir(parents=True, exist_ok=True)

    # Append to daily journal file
    journal_file = journal_dir / f"ingest-{today}.md"
    entry = f"\n\n## {now} — {raw_filename}\n\n**摘要**：{summary}\n\n{journal_entry}\n"

    if journal_file.exists():
        existing = journal_file.read_text(encoding="utf-8")
        _atomic_write(journal_file, existing + entry)
    else:
        header = f"# 编译日志 {today}\n"
        _atomic_write(journal_file, header + entry)


def compile_file(
    raw_file: Path,
    config: Config,
    state: WikiState,
    llm: LLMClient,
) -> list[str]:
    """Compile a single raw file into wiki entries. Returns affected wiki paths."""
    raw_content = _read_file_safe(raw_file)
    index_content = _get_index_content(config)
    schema_content = _get_schema_content(config)
    existing_stems = _get_existing_wiki_stems(config)

    prompt = build_ingest_prompt(
        raw_content=raw_content,
        raw_filename=raw_file.name,
        existing_index=index_content,
        schema_content=schema_content,
        existing_wiki_stems=existing_stems,
    )

    console.print(f"\n[dim]Compiling[/dim] [bold]{raw_file.name}[/bold]...")
    response = llm.complete(INGEST_SYSTEM, prompt, operation="ingest")

    try:
        result = _parse_llm_response(response)
    except CompileError as e:
        console.print(f"  [red]✗ parse error:[/red] {e}")
        raise

    actions = result.get("actions", [])
    summary = result.get("summary", "（无摘要）")
    journal_entry = result.get("journal_entry", "")

    affected = _apply_actions(actions, config)

    # Update index.md
    _update_index(config)

    # Write journal
    _write_journal(config, raw_file.name, journal_entry, summary)

    return affected


def _update_index(config: Config):
    """Regenerate wiki/index.md from actual file structure."""
    wiki_dir = config.wiki_dir
    if not wiki_dir.exists():
        return

    lines = [
        "# 知识库索引\n",
        f"_最后更新：{date.today().isoformat()}_\n\n",
    ]

    subdirs = [d for d in sorted(wiki_dir.iterdir()) if d.is_dir() and d.name != "journal"]
    for subdir in subdirs:
        md_files = sorted(subdir.glob("*.md"))
        if not md_files:
            continue
        lines.append(f"## {subdir.name}\n\n")
        for f in md_files:
            try:
                import frontmatter as fm
                post = fm.load(str(f))
                title = post.get("title", f.stem)
            except Exception:
                title = f.stem
            rel = f.relative_to(wiki_dir)
            lines.append(f"- [[{f.stem}]] — {title}\n")
        lines.append("\n")

    index_path = wiki_dir / "index.md"
    _atomic_write(index_path, "".join(lines))
