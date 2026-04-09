"""wiki search command - full-text search across wiki."""
import subprocess
from pathlib import Path

import click
from rich.console import Console
from rich.syntax import Syntax

from ..core.config import Config

console = Console()


def search_command(config: Config, keyword: str, context_lines: int = 2):
    """Full-text search in wiki using ripgrep/grep."""
    if not config.wiki_dir.exists():
        console.print("[red]Wiki directory not found.[/red]")
        return

    # Try rg first, then grep
    results = _run_search(keyword, config.wiki_dir, context_lines)
    if results is None:
        console.print(f"[red]Search failed[/red] (tried rg and grep)")
        return

    if not results:
        console.print(f"[dim]No results found for: {keyword}[/dim]")
        return

    console.print(results)


def _run_search(keyword: str, wiki_dir: Path, context_lines: int) -> str | None:
    """Run search, return output string or None on failure."""
    for cmd_template in [
        ["rg", "--color=always", f"-C{context_lines}", "-i", "--glob", "*.md",
         "--heading", keyword, str(wiki_dir)],
        ["grep", "-r", "--color=always", f"-C{context_lines}", "-i",
         "--include=*.md", keyword, str(wiki_dir)],
    ]:
        try:
            result = subprocess.run(
                cmd_template,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode in (0, 1):  # 1 = no matches (not an error)
                return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return None
