"""Wikilink parsing and fixing utilities."""
import re
from pathlib import Path


WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*)?\]\]")
# Matches the full [[link]] or [[link|text]], captures the stem part
WIKILINK_FULL_RE = re.compile(r"\[\[([^\]|#]+?)([|#][^\]]*?)?\]\]")


def extract_links(content: str) -> list[str]:
    """Extract all [[wikilink]] targets (stem only) from markdown content."""
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


def get_valid_stems(wiki_dir: Path) -> set[str]:
    """Get all valid wikilink stems from wiki directory."""
    stems = set()
    for p in wiki_dir.rglob("*.md"):
        if p.name == "index.md":
            continue
        stems.add(p.stem)
    return stems


def fuzzy_match_stem(link: str, valid_stems: set[str]) -> str | None:
    """Find the best matching valid stem for a broken wikilink."""
    if not link or len(link) < 2:
        return None

    link_lower = link.lower()

    # Exact case-insensitive match
    for stem in valid_stems:
        if stem.lower() == link_lower:
            return stem

    # Substring match
    candidates = []
    for stem in valid_stems:
        stem_lower = stem.lower()
        if link_lower in stem_lower or stem_lower in link_lower:
            candidates.append(stem)

    if len(candidates) == 1:
        return candidates[0]

    # Word-level overlap
    if not candidates:
        link_words = set(re.split(r'[-_]', link_lower))
        for stem in valid_stems:
            stem_words = set(re.split(r'[-_]', stem.lower()))
            overlap = len(link_words & stem_words)
            if overlap > 0 and overlap / max(len(link_words), 1) >= 0.4:
                candidates.append(stem)

    if len(candidates) == 1:
        return candidates[0]
    return None


def fix_wikilinks_in_content(content: str, valid_stems: set[str]) -> tuple[str, list[str]]:
    """Fix broken wikilinks in content string.

    Returns (fixed_content, list_of_fix_descriptions).
    Handles both [[stem]] and [[stem|display text]] formats.
    """
    fixes = []
    original = content

    for match in WIKILINK_FULL_RE.finditer(content):
        stem = match.group(1).strip()
        pipe_part = match.group(2) or ""  # e.g. "|显示文本"

        if stem in valid_stems:
            continue  # already valid

        # Try fuzzy match
        fixed_stem = fuzzy_match_stem(stem, valid_stems)
        full_match = match.group(0)  # [[stem|text]] or [[stem]]

        if fixed_stem:
            replacement = f"[[{fixed_stem}{pipe_part}]]"
            content = content.replace(full_match, replacement, 1)
            fixes.append(f"[[{stem}{pipe_part}]] → [[{fixed_stem}{pipe_part}]]")
        else:
            # Escape: make it plain text
            display = pipe_part.lstrip("|") if pipe_part else stem
            content = content.replace(full_match, f"`{display}`", 1)
            fixes.append(f"[[{stem}{pipe_part}]] → `{display}` (escaped)")

    return content, fixes


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
