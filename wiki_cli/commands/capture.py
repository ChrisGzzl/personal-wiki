"""wiki capture command - save content to raw/ without compilation."""
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
import sys

import click
from rich.console import Console

from ..core.config import Config

console = Console()


def capture_command(
    config: Config,
    text: str | None = None,
    file: Path | None = None,
    url: str | None = None,
    stdin: bool = False,
):
    """Capture content into raw/ for later compilation.

    This command only saves content — it does NOT trigger compilation.
    Run `wiki compile` separately to compile raw files.
    """
    if text:
        _capture_text(text, config)
    elif file:
        _capture_file(file, config)
    elif url:
        _capture_url(url, config)
    elif stdin:
        _capture_stdin(config)
    else:
        console.print("[yellow]Provide one of: --text, --file, --url, or --stdin[/yellow]")
        console.print("Example: wiki capture --text '今天学到了...'")


def _make_frontmatter(source: str, trigger: str = "manual", extra: dict | None = None) -> str:
    """Generate frontmatter for captured files."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = date.today().isoformat()
    extra = extra or {}
    # Extra keys override defaults
    title = extra.pop("title", f"Captured {today}")
    lines = [
        "---",
        f'title: "{title}"',
        f'source: "{source}"',
        f'capture_trigger: "{trigger}"',
        f'date_added: "{today}"',
        f'captured_at: "{now}"',
        "tags: []",
    ]
    for k, v in extra.items():
        lines.append(f'{k}: "{v}"')
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _capture_text(text: str, config: Config):
    """Save text to raw/notes/."""
    today = date.today().isoformat()
    notes_dir = config.raw_dir / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(notes_dir.glob(f"note-{today}-*.md"))
    idx = len(existing) + 1
    filename = f"note-{today}-{idx:03d}.md"
    raw_path = notes_dir / filename

    frontmatter = _make_frontmatter("manual input", extra={"title": f"Note {today}-{idx:03d}"})
    raw_path.write_text(frontmatter + text, encoding="utf-8")
    console.print(f"[green]✓ Captured to[/green] {raw_path.relative_to(config.wiki_root)}")


def _capture_file(file: Path, config: Config):
    """Copy file to raw/misc/."""
    file = file.expanduser().resolve()
    if not file.exists():
        raise click.ClickException(f"File not found: {file}")

    dest_dir = config.raw_dir / "misc"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.name

    if dest.exists():
        console.print(f"[yellow]Warning:[/yellow] {dest.name} already exists, overwriting.")

    shutil.copy2(file, dest)
    console.print(f"[green]✓ Captured to[/green] {dest.relative_to(config.wiki_root)}")


def _capture_url(url: str, config: Config):
    """Fetch URL and save to raw/articles/."""
    console.print(f"[dim]Fetching[/dim] {url}")
    try:
        from ..utils.fetcher import fetch_url, url_to_filename
        title, content = fetch_url(url)
    except Exception as e:
        console.print(f"[red]✗ Failed to fetch URL:[/red] {e}")
        return

    today = date.today().isoformat()
    filename = url_to_filename(url)
    raw_path = config.raw_dir / "articles" / filename
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = _make_frontmatter(
        source=url,
        trigger="manual",
        extra={"title": title},
    )
    raw_path.write_text(frontmatter + content, encoding="utf-8")
    console.print(f"[green]✓ Captured to[/green] {raw_path.relative_to(config.wiki_root)}")


def _capture_stdin(config: Config):
    """Read from stdin and save to raw/notes/."""
    if sys.stdin.isatty():
        console.print("[dim]Reading from stdin (Ctrl+D to finish)...[/dim]")

    text = sys.stdin.read()
    if not text.strip():
        console.print("[yellow]Empty input, nothing captured.[/yellow]")
        return

    _capture_text(text.strip(), config)
