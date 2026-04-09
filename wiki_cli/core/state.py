"""State management - reads/writes .wiki_state.json."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import Config


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()[:16]}"


class WikiState:
    def __init__(self, config: Config):
        self.config = config
        self._path = config.state_file
        self._data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path) as f:
                return json.load(f)
        return {
            "version": "1.0",
            "last_ingest": None,
            "last_lint": None,
            "processed_raw_files": [],
            "wiki_stats": {
                "total_pages": 0,
                "total_raw_files": 0,
                "unprocessed_raw_files": 0,
                "orphan_pages": 0,
                "broken_links": 0,
            },
        }

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get_processed_hashes(self) -> dict[str, str]:
        """Returns {relative_path: hash} for all processed files."""
        return {
            entry["path"]: entry["hash"]
            for entry in self._data.get("processed_raw_files", [])
        }

    def get_unprocessed_files(self, batch_size: int = 10) -> list[Path]:
        """Returns raw files not yet processed (or changed since last process)."""
        processed = self.get_processed_hashes()
        raw_dir = self.config.raw_dir
        if not raw_dir.exists():
            return []

        unprocessed = []
        for path in sorted(raw_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(self.config.wiki_root))
            current_hash = _file_hash(path)
            if processed.get(rel) != current_hash:
                unprocessed.append(path)
            if len(unprocessed) >= batch_size:
                break
        return unprocessed

    def mark_processed(self, path: Path, affected_wiki_pages: list[str]):
        rel = str(path.relative_to(self.config.wiki_root))
        current_hash = _file_hash(path)
        now = datetime.now(timezone.utc).isoformat()

        # Update or insert
        entries = self._data["processed_raw_files"]
        for entry in entries:
            if entry["path"] == rel:
                entry["hash"] = current_hash
                entry["processed_at"] = now
                entry["affected_wiki_pages"] = affected_wiki_pages
                self.save()
                return
        entries.append(
            {
                "path": rel,
                "hash": current_hash,
                "processed_at": now,
                "affected_wiki_pages": affected_wiki_pages,
            }
        )
        self.save()

    def update_last_ingest(self):
        self._data["last_ingest"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def update_last_lint(self):
        self._data["last_lint"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def update_stats(self, **kwargs):
        self._data["wiki_stats"].update(kwargs)
        self.save()

    @property
    def last_ingest(self) -> Optional[str]:
        return self._data.get("last_ingest")

    @property
    def last_lint(self) -> Optional[str]:
        return self._data.get("last_lint")

    @property
    def wiki_stats(self) -> dict:
        return self._data.get("wiki_stats", {})
