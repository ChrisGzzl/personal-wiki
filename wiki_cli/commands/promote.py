"""wiki promote command - elevate an output to wiki entry.

Human review is mandatory: the LLM-generated plan is shown before any write.
Use --dry-run to preview without writing, or --yes to skip the confirmation prompt.
"""
import shutil
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule

from ..core.compiler import compile_file, _parse_llm_response, _get_index_content, _get_schema_content
from ..core.config import Config
from ..core.llm import LLMClient
from ..core.state import WikiState
from ..prompts.ingest import INGEST_SYSTEM, build_ingest_prompt

console = Console()


def promote_command(config: Config, output_file: str, dry_run: bool = False, yes: bool = False):
    """Promote an output Q&A to a wiki entry, with mandatory human review.

    Default behavior:
    - Shows LLM's proposed wiki changes (dry-run preview)
    - Asks for confirmation before writing anything
    - Use --dry-run to only preview, never write
    - Use --yes to skip the confirmation prompt (automation mode)
    """
    path = _resolve_output_path(output_file, config)
    console.print(f"\n[bold]Promoting:[/bold] {path.name}\n")

    # Show the content being promoted
    content = path.read_text(encoding="utf-8")
    console.print(Panel(Markdown(content[:2000]), title="Content to promote", border_style="dim"))

    # Generate the LLM plan (dry-run first, always)
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

    # Always show the plan for review
    _show_plan(result)

    if dry_run:
        console.print("\n[yellow]--dry-run: no files written.[/yellow]")
        return

    # Require human confirmation before writing
    if not yes:
        console.print()
        confirmed = click.confirm(
            "Apply these changes to your wiki?",
            default=False,  # default No - safer
        )
        if not confirmed:
            console.print("[dim]Aborted. Nothing written.[/dim]")
            return

    # Apply
    temp_raw = config.raw_dir / "misc" / f"promoted-{path.name}"
    temp_raw.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, temp_raw)

    try:
        from ..core.compiler import _apply_actions, _write_journal, _update_index
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
            console.print(Panel(content_preview + ("..." if len(action.get("content","")) > 400 else ""),
                                border_style="dim", padding=(0, 1)))
        elif action_type == "update":
            section = action.get("section", "")
            append_preview = action.get("append", "")[:300]
            console.print(f"  [dim]section:[/dim] {section}")
            console.print(Panel(append_preview + ("..." if len(action.get("append","")) > 300 else ""),
                                border_style="dim", padding=(0, 1)))
    console.print(Rule())


def _resolve_output_path(output_file: str, config: Config) -> Path:
    p = Path(output_file).expanduser()
    if p.exists():
        return p

    candidate = config.outputs_dir / output_file
    if candidate.exists():
        return candidate

    if config.outputs_dir.exists():
        matches = list(config.outputs_dir.glob(f"*{output_file}*"))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            console.print("Multiple matches:")
            for m in matches:
                console.print(f"  {m.name}")
            raise click.ClickException("Specify a more exact name.")

    raise click.ClickException(f"Output file not found: {output_file}")


def _mark_promoted(path: Path):
    try:
        content = path.read_text(encoding="utf-8")
        content = content.replace("promoted_to_wiki: false", "promoted_to_wiki: true")
        path.write_text(content, encoding="utf-8")
    except Exception:
        pass
