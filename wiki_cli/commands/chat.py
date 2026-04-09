"""wiki chat command - interactive conversation mode."""
import click
from rich.console import Console
from rich.prompt import Prompt

from ..core.config import Config
from .ingest import ingest_command
from .query import query_command
from .status import status_command
from .lint import lint_command

console = Console()

HELP_TEXT = """
[bold]Wiki Chat Mode[/bold]
  Type a question to query your wiki.
  
  Commands:
    /ingest <url>     — Ingest a URL
    /ingest --text    — Enter text to ingest (prompts for input)
    /lint             — Run health check
    /status           — Show wiki status
    /help             — Show this help
    /quit or /exit    — Exit chat mode
"""


def chat_command(config: Config):
    """Enter interactive chat mode."""
    console.print(HELP_TEXT)
    console.print(f"[dim]Wiki root: {config.wiki_root}[/dim]\n")

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]wiki>[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "/q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        elif user_input.lower() == "/help":
            console.print(HELP_TEXT)

        elif user_input.lower() == "/status":
            status_command(config)

        elif user_input.lower() == "/lint":
            lint_command(config)

        elif user_input.startswith("/ingest "):
            arg = user_input[8:].strip()
            if arg.startswith("http"):
                ingest_command(config, url=arg)
            elif arg == "--text":
                text = Prompt.ask("Enter text to ingest")
                ingest_command(config, text=text)
            else:
                from pathlib import Path
                ingest_command(config, file=Path(arg))

        elif user_input.startswith("/"):
            console.print(f"[yellow]Unknown command:[/yellow] {user_input}")
            console.print("Type /help for available commands.")

        else:
            # Treat as a query
            query_command(config, question=user_input)

        console.print()
