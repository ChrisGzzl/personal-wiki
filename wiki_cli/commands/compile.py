"""wiki compile command - compile raw materials into staged drafts (compiled/).

This is the core v0.2.0 command, replacing the compile-then-write-to-wiki
behavior of v0.1.0's ingest. Compile outputs go to compiled/YYYY/MM/,
not directly to wiki/.
"""
from datetime import date, datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..core.compiler import compile_raw_to_staging
from ..core.config import Config
from ..core.llm import LLMClient
from ..core.state import WikiState

console = Console()


def compile_command(
    config: Config,
    raw_file: Path | None = None,
    batch_size: int | None = None,
):
    """Compile raw materials into staged drafts in compiled/."""
    state = WikiState(config)
    llm = LLMClient(config)

    if raw_file:
        # Compile a specific raw file
        raw_path = raw_file.expanduser().resolve()
        if not raw_path.exists():
            # Try under raw_dir
            candidate = config.raw_dir / raw_file
            if candidate.exists():
                raw_path = candidate
            else:
                console.print(f"[red]✗ File not found:[/red] {raw_file}")
                return

        console.print(f"[bold]Compiling[/bold] {raw_path.name}...")
        try:
            result = compile_raw_to_staging(raw_path, config, state, llm)
            if result:
                console.print(f"[green]✓ Compiled to[/green] {result}")
            else:
                console.print(f"[yellow]✗ Compilation produced no output[/yellow]")
        except Exception as e:
            console.print(f"[red]✗ Error:[/red] {e}")
        return

    # Default: scan raw/ for unprocessed files
    max_batch = batch_size or config.get("behavior.max_raw_batch", 10)
    unprocessed = state.get_unprocessed_files(batch_size=max_batch)

    if not unprocessed:
        console.print("[green]✓ Nothing new to compile.[/green]")
        return

    console.print(f"[bold]Found {len(unprocessed)} file(s) to compile.[/bold]")

    compiled_count = 0
    errors = []

    for raw_f in unprocessed:
        try:
            result = compile_raw_to_staging(raw_f, config, state, llm)
            if result:
                compiled_count += 1
                console.print(f"  [green]✓[/green] {raw_f.name} → {result}")
            else:
                console.print(f"  [yellow]⊘[/yellow] {raw_f.name} — no output produced")
        except Exception as e:
            errors.append((raw_f, str(e)))
            console.print(f"  [red]✗[/red] {raw_f.name} — {e}")

    console.print(
        f"\n[bold green]Done.[/bold green] "
        f"{compiled_count} compiled, "
        f"{len(errors)} errors."
    )

    state.update_last_compile()

    if compiled_count > 0:
        console.print(
            f"\n[dim]Run [cyan]wiki promote[/cyan] to review {compiled_count} compiled draft(s).[/dim]"
        )
