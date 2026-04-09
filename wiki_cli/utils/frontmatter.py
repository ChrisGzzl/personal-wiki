"""YAML frontmatter handling for wiki entries."""
from datetime import date
from pathlib import Path
from typing import Any

import frontmatter


def parse(path: Path) -> tuple[dict, str]:
    """Parse a markdown file, returns (metadata, content)."""
    post = frontmatter.load(str(path))
    return dict(post.metadata), post.content


def dump(metadata: dict, content: str) -> str:
    """Render metadata + content to markdown string with frontmatter."""
    post = frontmatter.Post(content, **metadata)
    return frontmatter.dumps(post)


def ensure_dates(metadata: dict) -> dict:
    """Ensure created/updated dates exist."""
    today = date.today().isoformat()
    if "created" not in metadata:
        metadata["created"] = today
    metadata["updated"] = today
    return metadata


def validate(path: Path) -> list[str]:
    """Basic validation, returns list of error messages."""
    errors = []
    try:
        meta, _ = parse(path)
        for field in ("title", "created", "updated", "tags"):
            if field not in meta:
                errors.append(f"Missing frontmatter field: {field}")
    except Exception as e:
        errors.append(f"Failed to parse frontmatter: {e}")
    return errors
