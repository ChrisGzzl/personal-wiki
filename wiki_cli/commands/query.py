"""wiki query command - ask questions against the wiki knowledge base."""
import re
import subprocess
from datetime import date
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown

from ..core.config import Config
from ..core.llm import LLMClient
from ..prompts.query import QUERY_SYSTEM, build_query_prompt

console = Console()


def _find_relevant_wiki_files(question: str, wiki_dir: Path, max_files: int = 8) -> list[Path]:
    """Use grep to find relevant wiki files without calling LLM."""
    if not wiki_dir.exists():
        return []

    # Extract meaningful keywords (skip short words)
    words = [w for w in re.split(r'\W+', question) if len(w) >= 3]
    if not words:
        return []

    # Search with ripgrep if available, fallback to grep
    found_files: set[Path] = set()

    for word in words[:6]:  # limit keywords
        try:
            # Try rg first, then grep
            for cmd in [
                ["rg", "-l", "-i", "--glob", "*.md", word, str(wiki_dir)],
                ["grep", "-r", "-l", "-i", word, str(wiki_dir), "--include=*.md"],
            ]:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        p = Path(line.strip())
                        if p.is_file():
                            found_files.add(p)
                    break
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    # Always include index.md
    index = wiki_dir / "index.md"
    if index.exists():
        found_files.add(index)

    return list(found_files)[:max_files]


def _build_wiki_context(files: list[Path], wiki_dir: Path, max_chars: int = 30000) -> str:
    """Build context string from relevant wiki files."""
    if not files:
        return "（知识库为空或未找到相关条目）"

    parts = []
    total = 0
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            rel = f.relative_to(wiki_dir)
            header = f"\n### [{rel}]\n"
            entry = header + content[:4000]
            if len(content) > 4000:
                entry += f"\n[... {len(content) - 4000} chars truncated ...]"
            parts.append(entry)
            total += len(entry)
            if total > max_chars:
                break
        except Exception:
            continue
    return "\n".join(parts)


def query_command(
    config: Config,
    question: str,
    deep: bool = False,
    save: bool = False,
):
    """Query the knowledge base."""
    llm = LLMClient(config)

    # Find relevant files
    relevant_files = _find_relevant_wiki_files(question, config.wiki_dir)
    if relevant_files:
        console.print(f"[dim]Found {len(relevant_files)} relevant wiki file(s)[/dim]")

    wiki_context = _build_wiki_context(relevant_files, config.wiki_dir)
    schema_content = ""
    if config.schema_file.exists():
        schema_content = config.schema_file.read_text(encoding="utf-8")[:3000]

    prompt = build_query_prompt(
        question=question,
        wiki_context=wiki_context,
        schema_content=schema_content,
        deep=deep,
    )

    console.print()
    # Use non-streaming for better compatibility with OpenAI-compatible providers
    answer = llm.complete(QUERY_SYSTEM, prompt, operation="query")
    console.print(Markdown(answer))

    # Offer to save
    if not save:
        console.print()
        save = click.confirm("Save this answer to outputs/?", default=False)

    if save:
        _save_output(question, answer, config)


def _save_output(question: str, answer: str, config: Config):
    """Save a Q&A pair to outputs/."""
    today = date.today().isoformat()
    config.outputs_dir.mkdir(parents=True, exist_ok=True)

    # Generate slug from question
    slug = re.sub(r'[^\w\-]', '-', question[:40]).strip('-').lower()
    slug = re.sub(r'-+', '-', slug)

    existing = sorted(config.outputs_dir.glob(f"{today}_{slug}*.md"))
    idx = len(existing) + 1
    filename = f"{today}_{slug}_{idx:02d}.md" if idx > 1 else f"{today}_{slug}.md"

    content = (
        f"---\n"
        f"question: \"{question}\"\n"
        f"date: \"{today}\"\n"
        f"promoted_to_wiki: false\n"
        f"---\n\n"
        f"## 问题\n\n{question}\n\n"
        f"## 回答\n\n{answer}\n"
    )

    output_path = config.outputs_dir / filename
    output_path.write_text(content, encoding="utf-8")
    console.print(f"\n[green]✓ Saved to[/green] {output_path.relative_to(config.wiki_root)}")
    console.print(f"[dim]Run `wiki promote {filename}` to add this to your wiki[/dim]")
