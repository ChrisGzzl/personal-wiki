"""Wikilink parsing utilities."""
import re
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*)?\]\]")


def extract_links(content: str) -> list[str]:
    """Extract all [[wikilink]] targets from markdown content."""
    return WIKILINK_RE.findall(content)


def resolve_link(link_target: str, wiki_dir: Path) -> Path | None:
    """Try to find the file a [[wikilink]] points to."""
    # Try direct match with .md extension in any subdir
    candidates = list(wiki_dir.rglob(f"{link_target}.md"))
    if candidates:
        return candidates[0]
    # Try case-insensitive
    lower = link_target.lower()
    for p in wiki_dir.rglob("*.md"):
        if p.stem.lower() == lower:
            return p
    return None


def find_broken_links(wiki_dir: Path) -> list[tuple[Path, str]]:
    """Return list of (file_path, broken_link_target)."""
    broken = []
    for md_file in wiki_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for link in extract_links(content):
            if resolve_link(link, wiki_dir) is None:
                broken.append((md_file, link))
    return broken


def find_orphan_pages(wiki_dir: Path) -> list[Path]:
    """Return pages not linked from any other page (excluding index.md)."""
    all_pages = {p for p in wiki_dir.rglob("*.md")}
    index_file = wiki_dir / "index.md"
    referenced = set()

    for md_file in all_pages:
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for link in extract_links(content):
            resolved = resolve_link(link, wiki_dir)
            if resolved:
                referenced.add(resolved)

    orphans = []
    for page in all_pages:
        if page == index_file:
            continue
        if page not in referenced:
            orphans.append(page)
    return orphans
