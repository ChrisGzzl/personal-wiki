"""wiki status command - show knowledge base statistics."""
from datetime import date, datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..core.config import Config
from ..core.state import WikiState

console = Console()


def status_command(config: Config):
    """Show knowledge base status without calling LLM."""
    if not config.wiki_root.exists():
        console.print(
            f"[red]Wiki not initialized.[/red] Run `wiki init {config.wiki_root}` first."
        )
        return

    state = WikiState(config)

    # Count files
    raw_count = _count_files(config.raw_dir, exclude={"archive"})
    archive_count = _count_files(config.raw_archive_dir)
    compiled_count = _count_files(config.compiled_dir)
    wiki_count = _count_files(config.wiki_dir, exclude={"journal", "index.md"})
    outputs_count = _count_files(config.outputs_dir)

    unprocessed = len(state.get_unprocessed_files(batch_size=9999))
    pending_compiled = len(state.get_pending_compiled())

    # Build table
    table = Table(title=f"Wiki Status — {config.wiki_root}", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold")

    table.add_row("Raw materials", str(raw_count))
    if archive_count:
        table.add_row("Archived raw files", f"[dim]{archive_count}[/dim]")
    table.add_row("Unprocessed raw files", f"[yellow]{unprocessed}[/yellow]" if unprocessed else "0")
    table.add_row("Compiled drafts", str(compiled_count))
    table.add_row("Pending review", f"[yellow]{pending_compiled}[/yellow]" if pending_compiled else "0")
    table.add_row("Wiki pages", str(wiki_count))
    table.add_row("Saved outputs", str(outputs_count))

    # Timestamps
    if state.last_compile:
        table.add_row("Last compile", _format_time(state.last_compile))
    elif state.last_ingest:
        table.add_row("Last compile", _format_time(state.last_ingest))
    else:
        table.add_row("Last compile", "[dim]never[/dim]")

    if state.last_audit:
        table.add_row("Last audit", _format_time(state.last_audit))
    else:
        table.add_row("Last audit", "[dim]never[/dim]")

    if state.last_lint:
        table.add_row("Last lint", _format_time(state.last_lint))
    else:
        table.add_row("Last lint", "[dim]never[/dim]")

    if state.last_gc:
        table.add_row("Last GC", _format_time(state.last_gc))
    else:
        table.add_row("Last GC", "[dim]never[/dim]")

    console.print(table)

    # Show subdirectory breakdown
    if config.wiki_dir.exists():
        sub_table = Table(title="Wiki Pages by Category", show_header=True, show_edge=False)
        sub_table.add_column("Category", style="dim")
        sub_table.add_column("Pages")

        for subdir in sorted(config.wiki_dir.iterdir()):
            if subdir.is_dir() and subdir.name != "journal":
                count = len(list(subdir.glob("*.md")))
                if count:
                    sub_table.add_row(subdir.name, str(count))

        console.print(sub_table)

    # Tips
    tips = []
    if unprocessed:
        tips.append(f"Run [cyan]wiki compile[/cyan] to compile {unprocessed} pending file(s)")
    if pending_compiled:
        tips.append(f"Run [cyan]wiki promote[/cyan] to review {pending_compiled} compiled draft(s)")
    if archive_count:
        tips.append(f"Run [cyan]wiki gc[/cyan] to clean up {archive_count} archived file(s)")

    if tips:
        console.print(f"\n[yellow]Tips:[/yellow]")
        for tip in tips:
            console.print(f"  • {tip}")


def _count_files(directory: Path, exclude: set[str] | None = None) -> int:
    if not directory.exists():
        return 0
    exclude = exclude or set()
    count = 0
    for p in directory.rglob("*"):
        if p.is_file() and p.name not in exclude and p.stem not in exclude:
            # Skip files in excluded subdirectories
            if any(part in exclude for part in p.parts):
                continue
            count += 1
    return count


def _format_time(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso_str
