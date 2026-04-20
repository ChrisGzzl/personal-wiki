"""Main CLI entry point for wiki tool."""
from pathlib import Path

import click
from rich.console import Console

console = Console()


def _get_config(wiki_root: str | None) -> "Config":
    from wiki_cli.core.config import Config
    root = Path(wiki_root) if wiki_root else None
    return Config(wiki_root=root)


@click.group()
@click.version_option(version="0.2.0", prog_name="wiki")
def cli():
    """LLM Wiki — Personal Knowledge Base CLI (Karpathy-style).

    Compile raw materials into structured wiki, query with LLM, keep knowledge growing.
    """
    pass


@cli.command()
@click.argument("wiki_root", default="~/wiki", metavar="[WIKI_ROOT]")
def init(wiki_root: str):
    """Initialize a new wiki knowledge base at WIKI_ROOT (default: ~/wiki)."""
    from wiki_cli.commands.init import init_command
    init_command(Path(wiki_root))


@cli.command()
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory (overrides WIKI_ROOT env var)")
@click.option("--url", default=None, help="Fetch and capture a URL to raw/")
@click.option("--text", default=None, help="Capture raw text to raw/")
@click.option("--file", "file_path", default=None, type=click.Path(), help="Capture a local file to raw/")
@click.option("--stdin", is_flag=True, default=False, help="Read content from stdin")
def capture(wiki_root, url, text, file_path, stdin):
    """Capture content into raw/ for later compilation.

    This command only saves content — it does NOT compile.
    Run `wiki compile` separately to compile raw files.
    """
    from wiki_cli.commands.capture import capture_command
    config = _get_config(wiki_root)
    file = Path(file_path) if file_path else None
    capture_command(config, url=url, text=text, file=file, stdin=stdin)


@cli.command()
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory (overrides WIKI_ROOT env var)")
@click.option("--file", "raw_file", default=None, type=click.Path(), help="Compile a specific raw file")
@click.option("--batch", default=None, type=int, help="Max files to process in one run")
def compile(wiki_root, raw_file, batch):
    """Compile raw materials into staged drafts (compiled/).

    Scans raw/ for unprocessed files and compiles them to compiled/YYYY/MM/.
    Use `wiki promote` to review and move compiled drafts into wiki/.
    """
    from wiki_cli.commands.compile import compile_command
    config = _get_config(wiki_root)
    file = Path(raw_file) if raw_file else None
    compile_command(config, raw_file=file, batch_size=batch)


@cli.command()
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory (overrides WIKI_ROOT env var)")
@click.option("--url", default=None, help="Fetch and ingest a URL")
@click.option("--text", default=None, help="Ingest raw text directly")
@click.option("--file", "file_path", default=None, type=click.Path(), help="Ingest a local file")
@click.option("--batch", default=None, type=int, help="Max files to process in one run")
def ingest(wiki_root, url, text, file_path, batch):
    """[DEPRECATED] Use 'wiki capture' + 'wiki compile' instead.

    This command is retained for backward compatibility.
    With --url/--text/--file: captures to raw/ then compiles.
    Without options: compiles raw/ (same as 'wiki compile').
    """
    console.print("[yellow]⚠ 'wiki ingest' is deprecated. Use 'wiki capture' + 'wiki compile' instead.[/yellow]")
    from wiki_cli.commands.ingest import ingest_command
    config = _get_config(wiki_root)
    file = Path(file_path) if file_path else None
    ingest_command(config, url=url, text=text, file=file, batch_size=batch)


@cli.command()
@click.argument("question")
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory")
@click.option("--deep", is_flag=True, default=False, help="Deep research mode (longer output)")
@click.option("--save", is_flag=True, default=False, help="Auto-save answer to outputs/")
def query(question, wiki_root, deep, save):
    """Ask a question against your wiki knowledge base."""
    from wiki_cli.commands.query import query_command
    config = _get_config(wiki_root)
    query_command(config, question=question, deep=deep, save=save)


@cli.command()
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory")
@click.option("--auto", is_flag=True, default=False, help="Auto-fix safe issues (update index, etc.)")
@click.option("--fix-links", is_flag=True, default=False, help="Fix broken wikilinks using fuzzy matching")
def lint(wiki_root, auto, fix_links):
    """Run health check on the knowledge base."""
    from wiki_cli.commands.lint import lint_command
    config = _get_config(wiki_root)
    lint_command(config, auto=auto, fix_links=fix_links)


@cli.command()
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory")
def status(wiki_root):
    """Show knowledge base statistics (no LLM calls)."""
    from wiki_cli.commands.status import status_command
    config = _get_config(wiki_root)
    status_command(config)


@cli.command()
@click.argument("keyword")
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory")
@click.option("--context", "-C", default=2, type=int, help="Lines of context around matches")
def search(keyword, wiki_root, context):
    """Full-text search across wiki entries (uses ripgrep/grep)."""
    from wiki_cli.commands.search import search_command
    config = _get_config(wiki_root)
    search_command(config, keyword=keyword, context_lines=context)


@cli.command()
@click.argument("output_file", required=False, default=None)
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory")
@click.option("--dry-run", is_flag=True, default=False, help="Preview proposed changes without writing")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt (automation mode)")
@click.option("--all", "promote_all", is_flag=True, default=False, help="Promote all pending compiled drafts")
@click.option("--reject", default=None, help="Reject a specific compiled file")
@click.option("--reason", default=None, help="Reason for rejection (used with --reject)")
def promote(output_file, wiki_root, dry_run, yes, promote_all, reject, reason):
    """Review and promote compiled drafts into wiki.

    Without arguments: list pending compiled drafts sorted by reference frequency.
    With a file argument: promote that compiled draft to wiki/.
    Use --reject <file> --reason "..." to reject and provide feedback.
    """
    from wiki_cli.commands.promote import promote_command
    config = _get_config(wiki_root)
    promote_command(
        config,
        output_file=output_file,
        dry_run=dry_run,
        yes=yes,
        promote_all=promote_all,
        reject=reject,
        reason=reason,
    )


@cli.command()
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory")
@click.option("--dry-run", is_flag=True, default=False, help="Preview what would be cleaned up")
@click.option("--force", is_flag=True, default=False, help="Skip confirmation prompt")
def gc(wiki_root, dry_run, force):
    """Garbage collect stale raw/ and compiled/ files.

    Rules:
    - raw/ files older than 90 days with no compiled output → archive
    - archived files older than 180 days → delete
    - compiled/ drafts pending >180 days → auto-reject
    """
    from wiki_cli.commands.gc import gc_command
    config = _get_config(wiki_root)
    gc_command(config, dry_run=dry_run, force=force)


@cli.command()
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory")
def chat(wiki_root):
    """Enter interactive chat mode with your wiki."""
    from wiki_cli.commands.chat import chat_command
    config = _get_config(wiki_root)
    chat_command(config)


@cli.command()
@click.argument("path_arg", required=False, metavar="[PATH]")
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory")
def browse(path_arg, wiki_root):
    """Browse wiki entries in the terminal (uses glow or rich)."""
    from wiki_cli.commands.browse import browse_command
    config = _get_config(wiki_root)
    browse_command(config, path_arg=path_arg)


@cli.command()
@click.option("--wiki-root", "-w", default=None, help="Wiki root directory")
@click.option("--last", default=5, type=int, help="Number of recent log entries to show")
def log(wiki_root, last):
    """Show recent compilation journal entries."""
    config = _get_config(wiki_root)
    journal_dir = config.wiki_dir / "journal"
    if not journal_dir.exists():
        console.print("[dim]No journal entries yet.[/dim]")
        return

    files = sorted(journal_dir.glob("ingest-*.md"), reverse=True)[:last]
    if not files:
        console.print("[dim]No ingest logs yet.[/dim]")
        return

    from rich.markdown import Markdown
    for f in files:
        content = f.read_text(encoding="utf-8")
        console.print(Markdown(content))
        console.rule()


if __name__ == "__main__":
    cli()
