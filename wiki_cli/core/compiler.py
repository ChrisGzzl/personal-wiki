"""Core compilation engine - the heart of wiki ingest."""
import json
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import Config
from .llm import LLMClient
from .state import WikiState
from ..prompts.ingest import INGEST_SYSTEM, build_ingest_prompt
from ..prompts.compile import COMPILE_SYSTEM, build_compile_prompt

console = Console()


class CompileError(Exception):
    pass


def _read_file_safe(path: Path, max_chars: int = 80000) -> str:
    """Read file, truncating if too large."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[... truncated at {max_chars} chars ...]"
        return text
    except Exception as e:
        return f"[Failed to read file: {e}]"


def _get_index_content(config: Config) -> str:
    index_path = config.wiki_dir / "index.md"
    if index_path.exists():
        return _read_file_safe(index_path, 10000)
    return "（知识库为空，尚无条目）"


def _get_schema_content(config: Config) -> str:
    if config.schema_file.exists():
        return _read_file_safe(config.schema_file, 8000)
    return "（无 schema.md，使用默认规则）"


def _fix_wikilinks(actions: list[dict], valid_stems: set[str]) -> list[dict]:
    """Fix broken wikilinks in action content before writing.

    Replaces [[invalid-link]] with the closest valid stem match,
    or removes the link if no reasonable match exists.
    """
    for action in actions:
        if action.get("type") != "create":
            continue

        content = action.get("content", "")
        if not content:
            continue

        # Find all [[wikilink]] references
        original = content
        for match in re.finditer(r'\[\[([^\]]+)\]\]', content):
            link = match.group(1)
            if link in valid_stems:
                continue  # already valid

            # Try to find a fuzzy match
            fixed = _fuzzy_match_stem(link, valid_stems)
            if fixed:
                content = content.replace(f"[[{link}]]", f"[[{fixed}]]")
                console.print(f"  [yellow]⟳ link fix:[/yellow] [[{link}]] → [[{fixed}]]")
            else:
                # No match: escape the link so it's not treated as wikilink
                content = content.replace(f"[[{link}]]", f"`[[{link}]]`")
                console.print(f"  [yellow]⟳ link fix:[/yellow] [[{link}]] → escaped (no match)")

        if content != original:
            action["content"] = content

    # Also fix wikilinks in update action append text
    for action in actions:
        if action.get("type") != "update":
            continue
        append_text = action.get("append", "")
        if not append_text:
            continue

        original = append_text
        for match in re.finditer(r'\[\[([^\]]+)\]\]', append_text):
            link = match.group(1)
            if link in valid_stems:
                continue
            fixed = _fuzzy_match_stem(link, valid_stems)
            if fixed:
                append_text = append_text.replace(f"[[{link}]]", f"[[{fixed}]]")
            else:
                append_text = append_text.replace(f"[[{link}]]", f"`[[{link}]]`")

        if append_text != original:
            action["append"] = append_text

    return actions


def _fuzzy_match_stem(link: str, valid_stems: set[str]) -> str | None:
    """Find the best matching valid stem for a broken wikilink.

    Handles common LLM mistakes: Chinese names, wrong naming conventions,
    close but not exact stem names.
    """
    # Skip obviously non-link content
    if not link or len(link) < 2:
        return None

    link_lower = link.lower()

    # Exact case-insensitive match
    for stem in valid_stems:
        if stem.lower() == link_lower:
            return stem

    # Check if link is a substring of a valid stem or vice versa
    candidates = []
    for stem in valid_stems:
        stem_lower = stem.lower()
        # Substring match
        if link_lower in stem_lower or stem_lower in link_lower:
            # Score by how much they overlap
            overlap = min(len(link_lower), len(stem_lower)) / max(len(link_lower), len(stem_lower))
            candidates.append((stem, overlap))

    # Also try word-level matching for hyphenated stems
    link_words = set(link_lower.replace("-", " ").split())
    for stem in valid_stems:
        stem_words = set(stem.lower().replace("-", " ").split())
        word_overlap = len(link_words & stem_words) / max(len(link_words | stem_words), 1)
        if word_overlap > 0.4:
            candidates.append((stem, word_overlap))

    if candidates:
        candidates.sort(key=lambda x: -x[1])
        best = candidates[0]
        if best[1] >= 0.4:
            return best[0]

    return None


def _dedup_actions(actions: list[dict], existing_stems: set[str], config: Config) -> list[dict]:
    """Deduplicate compile actions: convert create to update when content
    overlaps with an existing wiki entry.

    Checks both stem name and content keyword overlap to prevent duplicates.
    """
    deduped = []
    for action in actions:
        if action.get("type") != "create":
            deduped.append(action)
            continue

        action_path = action.get("path", "")
        stem = Path(action_path).stem if action_path else ""
        content = action.get("content", "")

        # Check 1: exact stem match
        if stem and stem in existing_stems:
            console.print(f"  [yellow]⟳ dedup:[/yellow] {stem} already exists, converting create → update")
            deduped.append({
                "type": "update",
                "path": action_path,
                "section": "## 关键观点",
                "append": _extract_key_points(content),
            })
            continue

        # Check 2: content overlap — extract keywords from new content
        # and check against existing wiki entries
        if content:
            overlap_stem, overlap_score = _find_content_overlap(content, config, existing_stems)
            if overlap_stem and overlap_score >= 0.4:
                console.print(f"  [yellow]⟳ dedup:[/yellow] content overlaps with {overlap_stem} (score={overlap_score:.2f}), converting create → update")
                # Find the actual wiki path for this stem
                wiki_path = _find_wiki_path_for_stem(overlap_stem, config)
                deduped.append({
                    "type": "update",
                    "path": wiki_path or action_path,
                    "section": "## 关键观点",
                    "append": _extract_key_points(content),
                })
                continue

        deduped.append(action)

    return deduped


def _find_content_overlap(content: str, config: Config, existing_stems: set[str]) -> tuple[str | None, float]:
    """Find the existing wiki entry with the highest keyword overlap.

    Returns (stem, score) or (None, 0.0) if no significant overlap.
    Uses keyword extraction + Jaccard-like similarity.
    """
    # Extract keywords from the new content (after frontmatter)
    new_keywords = _extract_keywords(content)
    if not new_keywords:
        return None, 0.0

    best_stem = None
    best_score = 0.0

    for stem in existing_stems:
        wiki_path = _find_wiki_path_for_stem(stem, config)
        if not wiki_path:
            continue
        full_path = config.wiki_root / wiki_path
        if not full_path.exists():
            continue

        try:
            existing_content = full_path.read_text(encoding="utf-8")[:8000]
        except Exception:
            continue

        existing_keywords = _extract_keywords(existing_content)
        if not existing_keywords:
            continue

        # Jaccard-like overlap score
        intersection = new_keywords & existing_keywords
        union = new_keywords | existing_keywords
        score = len(intersection) / len(union) if union else 0.0

        if score > best_score:
            best_score = score
            best_stem = stem

    return best_stem, best_score


def _extract_keywords(content: str, min_len: int = 3) -> set[str]:
    """Extract meaningful keywords from content for overlap comparison.

    Skips frontmatter, markdown syntax, and common stop words.
    """
    # Strip frontmatter
    fm_end = content.find("---", 4)
    if fm_end > 0:
        content = content[fm_end + 3:]

    # Strip markdown syntax
    content = re.sub(r'[#*\[\]()`>|_\-]', ' ', content)
    # Strip punctuation
    content = re.sub(r'[^\w\s]', ' ', content)

    # Common stop words (Chinese + English)
    stop_words = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
        "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
        "什么", "如何", "怎么", "为什么", "可以", "可能", "如果", "因为",
        "但是", "所以", "或者", "还是", "以及", "通过", "进行", "使用",
        "the", "and", "for", "are", "but", "not", "you", "all", "can",
        "had", "her", "was", "one", "our", "out", "this", "that", "with",
        "from", "they", "been", "have", "will", "what", "when", "which",
    }

    words = set()
    for w in re.split(r'\s+', content):
        w = w.strip().lower()
        if len(w) < min_len:
            continue
        if w in stop_words:
            continue
        # For Chinese: also add bigrams for better matching
        if any('\u4e00' <= c <= '\u9fff' for c in w):
            for i in range(len(w) - 1):
                bigram = w[i:i+2]
                if len(bigram) >= 2:
                    words.add(bigram)
        words.add(w)

    return words


def _find_wiki_path_for_stem(stem: str, config: Config) -> str | None:
    """Find the wiki/ path for a given stem."""
    if not config.wiki_dir.exists():
        return None
    for p in config.wiki_dir.rglob("*.md"):
        if p.stem == stem and p.parent.name != "journal":
            return str(p.relative_to(config.wiki_root))
    return None


def _extract_key_points(content: str) -> str:
    """Extract key points section from a compiled draft's content.

    Used when converting a 'create' action to an 'update' action during dedup.
    Falls back to a summary of the content if no 关键观点 section found.
    """
    # Try to extract the 关键观点 section
    match = re.search(r'^## 关键观点\s*\n(.*?)(?=\n## |\Z)', content, re.MULTILINE | re.DOTALL)
    if match and match.group(1).strip():
        return match.group(1).strip()

    # Fallback: extract bullet points from the content
    bullets = re.findall(r'^[-•]\s+.+$', content, re.MULTILINE)
    if bullets:
        return "\n".join(bullets)

    # Last resort: first 500 chars after frontmatter
    fm_end = content.find("---", 4)  # skip opening ---
    body = content[fm_end + 3:].strip() if fm_end > 0 else content
    return body[:500]


def _get_existing_wiki_stems(config: Config) -> list[str]:
    """Return all existing wiki page stems (filename without .md extension)."""
    if not config.wiki_dir.exists():
        return []
    stems = []
    for p in config.wiki_dir.rglob("*.md"):
        if p.name != "index.md" and p.parent.name != "journal":
            stems.append(p.stem)
    return stems


def _parse_llm_response(response: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Strip ```json ... ``` wrapper if present
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # Try to find raw JSON object
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            raise CompileError("LLM response contains no JSON object")
        json_str = match.group(0)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise CompileError(f"Failed to parse LLM JSON response: {e}")


def _atomic_write(path: Path, content: str):
    """Write content atomically using a temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
    ) as f:
        f.write(content)
        tmp_path = Path(f.name)
    tmp_path.replace(path)


def _apply_actions(actions: list[dict], config: Config) -> list[str]:
    """Apply create/update actions from LLM response. Returns affected paths."""
    affected = []
    today = date.today().isoformat()

    for action in actions:
        action_type = action.get("type")
        rel_path = action.get("path", "")
        if not rel_path:
            continue

        # Ensure path is under wiki_root
        target = config.wiki_root / rel_path
        affected.append(rel_path)

        if action_type == "create":
            content = action.get("content", "")
            if not content:
                continue
            _atomic_write(target, content)
            console.print(f"  [green]✓ created[/green] {rel_path}")

        elif action_type == "update":
            if not target.exists():
                # Create it if doesn't exist
                content = action.get("content", "")
                if content:
                    _atomic_write(target, content)
                    console.print(f"  [green]✓ created[/green] {rel_path}")
                continue

            existing = target.read_text(encoding="utf-8")
            section = action.get("section")
            append_text = action.get("append", "")

            if section and section in existing:
                # Append after the section header
                idx = existing.find(section)
                # Find the next ## heading or end of file
                next_section = re.search(r"\n## ", existing[idx + len(section) :])
                if next_section:
                    insert_pos = idx + len(section) + next_section.start()
                    new_content = (
                        existing[:insert_pos]
                        + f"\n\n{append_text}"
                        + existing[insert_pos:]
                    )
                else:
                    new_content = existing + f"\n\n{append_text}"
            else:
                new_content = existing + f"\n\n{append_text}"

            # Update the 'updated' date in frontmatter
            new_content = re.sub(
                r"^updated:.*$", f"updated: \"{today}\"", new_content, flags=re.MULTILINE
            )
            _atomic_write(target, new_content)
            console.print(f"  [blue]✓ updated[/blue] {rel_path}")

    return affected


def _write_journal(config: Config, raw_filename: str, journal_entry: str, summary: str):
    """Write a journal entry for this compilation."""
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    journal_dir = config.wiki_dir / "journal"
    journal_dir.mkdir(parents=True, exist_ok=True)

    # Append to daily journal file
    journal_file = journal_dir / f"ingest-{today}.md"
    entry = f"\n\n## {now} — {raw_filename}\n\n**摘要**：{summary}\n\n{journal_entry}\n"

    if journal_file.exists():
        existing = journal_file.read_text(encoding="utf-8")
        _atomic_write(journal_file, existing + entry)
    else:
        header = f"# 编译日志 {today}\n"
        _atomic_write(journal_file, header + entry)


def compile_file(
    raw_file: Path,
    config: Config,
    state: WikiState,
    llm: LLMClient,
) -> list[str]:
    """Compile a single raw file into wiki entries. Returns affected wiki paths."""
    raw_content = _read_file_safe(raw_file)
    index_content = _get_index_content(config)
    schema_content = _get_schema_content(config)
    existing_stems = _get_existing_wiki_stems(config)

    prompt = build_ingest_prompt(
        raw_content=raw_content,
        raw_filename=raw_file.name,
        existing_index=index_content,
        schema_content=schema_content,
        existing_wiki_stems=existing_stems,
    )

    console.print(f"\n[dim]Compiling[/dim] [bold]{raw_file.name}[/bold]...")
    response = llm.complete(INGEST_SYSTEM, prompt, operation="ingest")

    try:
        result = _parse_llm_response(response)
    except CompileError as e:
        console.print(f"  [red]✗ parse error:[/red] {e}")
        raise

    actions = result.get("actions", [])
    summary = result.get("summary", "（无摘要）")
    journal_entry = result.get("journal_entry", "")

    affected = _apply_actions(actions, config)

    # Update index.md
    _update_index(config)

    # Write journal
    _write_journal(config, raw_file.name, journal_entry, summary)

    return affected


def _update_index(config: Config):
    """Regenerate wiki/index.md from actual file structure."""
    wiki_dir = config.wiki_dir
    if not wiki_dir.exists():
        return

    lines = [
        "# 知识库索引\n",
        f"_最后更新：{date.today().isoformat()}_\n\n",
    ]

    subdirs = [d for d in sorted(wiki_dir.iterdir()) if d.is_dir() and d.name != "journal"]
    for subdir in subdirs:
        md_files = sorted(subdir.glob("*.md"))
        if not md_files:
            continue
        lines.append(f"## {subdir.name}\n\n")
        for f in md_files:
            try:
                import frontmatter as fm
                post = fm.load(str(f))
                title = post.get("title", f.stem)
            except Exception:
                title = f.stem
            rel = f.relative_to(wiki_dir)
            lines.append(f"- [[{f.stem}]] — {title}\n")
        lines.append("\n")

    index_path = wiki_dir / "index.md"
    _atomic_write(index_path, "".join(lines))


def _get_compile_feedback(config: Config) -> str:
    """Read compile_feedback.md for injection into compile prompt."""
    fb_path = config.compile_feedback_file
    if fb_path.exists():
        content = _read_file_safe(fb_path, 4000)
        # Skip the header comments
        lines = content.split("\n")
        body_lines = []
        in_header = True
        for line in lines:
            if in_header and not line.startswith("#"):
                in_header = False
            if not in_header:
                body_lines.append(line)
        return "\n".join(body_lines).strip()
    return ""


def _get_compiled_output_path(config: Config, raw_file: Path) -> Path:
    """Generate output path under compiled/YYYY/MM/ for a raw file."""
    today = date.today()
    dest_dir = config.compiled_dir / str(today.year) / f"{today.month:02d}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir / raw_file.stem


def compile_raw_to_staging(
    raw_file: Path,
    config: Config,
    state: WikiState,
    llm: LLMClient,
) -> str | None:
    """Compile a raw file into staged drafts in compiled/YYYY/MM/.

    Unlike compile_file() which writes directly to wiki/, this function
    outputs to the compiled/ staging area for later human review.

    Returns the path of the compiled output, or None if no output produced.
    """
    raw_content = _read_file_safe(raw_file)
    index_content = _get_index_content(config)
    schema_content = _get_schema_content(config)
    existing_stems = _get_existing_wiki_stems(config)
    compile_feedback = _get_compile_feedback(config)

    prompt = build_compile_prompt(
        raw_content=raw_content,
        raw_filename=raw_file.name,
        existing_index=index_content,
        schema_content=schema_content,
        existing_wiki_stems=existing_stems,
        compile_feedback=compile_feedback,
    )

    console.print(f"\n[dim]Compiling[/dim] [bold]{raw_file.name}[/bold]...")
    response = llm.complete(COMPILE_SYSTEM, prompt, operation="compile")

    try:
        result = _parse_llm_response(response)
    except CompileError as e:
        console.print(f"  [red]✗ parse error:[/red] {e}")
        raise

    actions = result.get("actions", [])
    summary = result.get("summary", "（无摘要）")
    journal_entry = result.get("journal_entry", "")

    if not actions:
        console.print(f"  [yellow]⊘[/yellow] No actions produced for {raw_file.name}")
        return None

    # Dedup: convert create actions to update if stem already exists in wiki/
    existing_stems_set = set(existing_stems)
    actions = _dedup_actions(actions, existing_stems_set, config)

    # Fix broken wikilinks in all actions before writing
    # Collect stems created by this batch so internal links are valid
    new_stems = set()
    for action in actions:
        if action.get("type") == "create":
            action_path = action.get("path", "")
            if action_path:
                new_stems.add(Path(action_path).stem)
    valid_stems = existing_stems_set | new_stems

    actions = _fix_wikilinks(actions, valid_stems)

    # Write each create action to compiled/
    compiled_path = _get_compiled_output_path(config, raw_file)
    written_files = []

    for action in actions:
        if action.get("type") == "create":
            content = action.get("content", "")
            if not content:
                continue
            # For creates, write to compiled/ as individual files
            action_path = action.get("path", "")
            if action_path:
                # Extract filename from the wiki path (e.g., wiki/concepts/xxx.md → xxx.md)
                filename = Path(action_path).name
            else:
                filename = f"{compiled_path.name}.md"

            out_path = compiled_path.parent / filename
            _atomic_write(out_path, content)
            written_files.append(str(out_path.relative_to(config.wiki_root)))
            console.print(f"  [green]✓ staged[/green] {out_path.relative_to(config.wiki_root)}")

        elif action.get("type") == "update":
            # For updates, store as a patch file alongside creates
            patch_data = {
                "type": "update",
                "path": action.get("path", ""),
                "section": action.get("section", ""),
                "append": action.get("append", ""),
            }
            patch_filename = f"patch-{compiled_path.name}.json"
            patch_path = compiled_path.parent / patch_filename
            _atomic_write(patch_path, json.dumps(patch_data, ensure_ascii=False, indent=2))
            written_files.append(str(patch_path.relative_to(config.wiki_root)))
            console.print(f"  [blue]✓ staged patch[/blue] {patch_path.relative_to(config.wiki_root)}")

    # Write journal
    _write_journal(config, raw_file.name, journal_entry, summary)

    # Mark as processed in state and record compiled file
    state.mark_processed(raw_file, [f"compiled/{compiled_path.relative_to(config.compiled_dir)}"])
    state.mark_compiled(str(compiled_path.relative_to(config.wiki_root)), str(raw_file.relative_to(config.wiki_root)))

    return str(compiled_path.relative_to(config.wiki_root)) if written_files else None
