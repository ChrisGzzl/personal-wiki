"""wiki browse command - render wiki files in terminal."""
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown

from ..core.config import Config

console = Console()


def browse_command(config: Config, path_arg: str | None = None):
    """Browse wiki entries in terminal."""
    if path_arg:
        target = config.wiki_dir / path_arg
        if not target.exists():
            # Try with .md extension
            target = config.wiki_dir / f"{path_arg}.md"
        if not target.exists():
            raise click.ClickException(f"Not found: {path_arg}")
    else:
        target = config.wiki_dir / "index.md"

    if target.is_file():
        _render_file(target)
    elif target.is_dir():
        _list_directory(target, config.wiki_dir)
    else:
        raise click.ClickException(f"Not a file or directory: {target}")


def _render_file(path: Path):
    """Render a markdown file. Try glow first, fallback to rich."""
    # Try glow
    try:
        result = subprocess.run(
            ["glow", str(path)],
            timeout=10,
        )
        if result.returncode == 0:
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback to rich
    content = path.read_text(encoding="utf-8")
    console.print(Markdown(content))


def _list_directory(directory: Path, wiki_dir: Path):
    """List .md files in a directory."""
    files = sorted(directory.glob("*.md"))
    if not files:
        console.print(f"[dim]No markdown files in {directory.relative_to(wiki_dir)}[/dim]")
        return

    console.print(f"\n[bold]{directory.relative_to(wiki_dir)}/[/bold]\n")
    for f in files:
        console.print(f"  {f.stem}")
    console.print(f"\n[dim]Use `wiki browse {directory.relative_to(wiki_dir)}/<name>` to read a file.[/dim]")
