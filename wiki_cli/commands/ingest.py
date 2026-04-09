"""wiki ingest command - compile raw materials into wiki entries."""
import shutil
from datetime import date
from pathlib import Path

import click
from rich.console import Console

from ..core.compiler import compile_file
from ..core.config import Config
from ..core.llm import LLMClient
from ..core.state import WikiState

console = Console()


def ingest_command(
    config: Config,
    url: str | None = None,
    text: str | None = None,
    file: Path | None = None,
    batch_size: int | None = None,
):
    """Main ingest logic - handles all three input modes."""
    state = WikiState(config)
    llm = LLMClient(config)

    # Mode: --url
    if url:
        raw_file = _ingest_from_url(url, config)
        if raw_file:
            _compile_one(raw_file, config, state, llm)
        return

    # Mode: --text
    if text:
        raw_file = _ingest_from_text(text, config)
        _compile_one(raw_file, config, state, llm)
        return

    # Mode: --file
    if file:
        raw_file = _ingest_from_file(file, config)
        _compile_one(raw_file, config, state, llm)
        return

    # Default: scan raw/ for unprocessed files
    max_batch = batch_size or config.get("behavior.max_raw_batch", 10)
    unprocessed = state.get_unprocessed_files(batch_size=max_batch)

    if not unprocessed:
        console.print("[green]✓ Nothing new to compile.[/green]")
        return

    console.print(f"[bold]Found {len(unprocessed)} file(s) to compile.[/bold]")

    total_affected = []
    errors = []
    for raw_file in unprocessed:
        try:
            affected = _compile_one(raw_file, config, state, llm)
            total_affected.extend(affected)
        except Exception as e:
            errors.append((raw_file, str(e)))
            console.print(f"  [red]✗ Error compiling {raw_file.name}:[/red] {e}")

    console.print(f"\n[bold green]Done.[/bold green] "
                  f"{len(unprocessed) - len(errors)} compiled, "
                  f"{len(errors)} errors, "
                  f"{len(set(total_affected))} wiki pages affected.")

    state.update_last_ingest()


def _compile_one(raw_file: Path, config: Config, state: WikiState, llm: LLMClient) -> list[str]:
    affected = compile_file(raw_file, config, state, llm)
    state.mark_processed(raw_file, affected)
    return affected


def _ingest_from_url(url: str, config: Config) -> Path | None:
    """Fetch URL, save to raw/articles/, return path."""
    console.print(f"[dim]Fetching[/dim] {url}")
    try:
        from ..utils.fetcher import fetch_url, url_to_filename
        title, content = fetch_url(url)
    except Exception as e:
        console.print(f"[red]✗ Failed to fetch URL:[/red] {e}")
        return None

    today = date.today().isoformat()
    filename = url_to_filename(url)
    raw_path = config.raw_dir / "articles" / filename
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = (
        f"---\n"
        f"title: \"{title}\"\n"
        f"source: \"{url}\"\n"
        f"date_added: \"{today}\"\n"
        f"tags: []\n"
        f"---\n\n"
    )
    raw_path.write_text(frontmatter + content, encoding="utf-8")
    console.print(f"[green]✓ Saved to[/green] {raw_path.relative_to(config.wiki_root)}")
    return raw_path


def _ingest_from_text(text: str, config: Config) -> Path:
    """Save text to raw/notes/, return path."""
    today = date.today().isoformat()
    # Generate sequential filename
    notes_dir = config.raw_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(notes_dir.glob(f"note-{today}-*.md"))
    idx = len(existing) + 1
    filename = f"note-{today}-{idx:03d}.md"
    raw_path = notes_dir / filename

    frontmatter = (
        f"---\n"
        f"title: \"Note {today}-{idx:03d}\"\n"
        f"source: \"manual input\"\n"
        f"date_added: \"{today}\"\n"
        f"tags: []\n"
        f"---\n\n"
    )
    raw_path.write_text(frontmatter + text, encoding="utf-8")
    console.print(f"[green]✓ Saved to[/green] {raw_path.relative_to(config.wiki_root)}")
    return raw_path


def _ingest_from_file(file: Path, config: Config) -> Path:
    """Copy file to raw/misc/, return path."""
    file = file.expanduser().resolve()
    if not file.exists():
        raise click.ClickException(f"File not found: {file}")

    dest_dir = config.raw_dir / "misc"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.name

    if dest.exists():
        console.print(f"[yellow]Warning:[/yellow] {dest.name} already exists, overwriting.")

    shutil.copy2(file, dest)
    console.print(f"[green]✓ Copied to[/green] {dest.relative_to(config.wiki_root)}")
    return dest
