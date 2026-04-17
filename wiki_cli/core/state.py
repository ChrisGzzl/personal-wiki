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
            "version": "2.0",
            "last_ingest": None,
            "last_lint": None,
            "last_compile": None,
            "last_gc": None,
            "last_audit": None,
            "processed_raw_files": [],
            "compiled_files": [],
            "wiki_stats": {
                "total_pages": 0,
                "total_raw_files": 0,
                "unprocessed_raw_files": 0,
                "pending_compiled": 0,
                "promoted_count": 0,
                "rejected_count": 0,
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

    def update_last_compile(self):
        self._data["last_compile"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def update_last_gc(self):
        self._data["last_gc"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def update_last_audit(self):
        self._data["last_audit"] = datetime.now(timezone.utc).isoformat()
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
    def last_compile(self) -> Optional[str]:
        return self._data.get("last_compile")

    @property
    def last_gc(self) -> Optional[str]:
        return self._data.get("last_gc")

    @property
    def last_audit(self) -> Optional[str]:
        return self._data.get("last_audit")

    @property
    def wiki_stats(self) -> dict:
        return self._data.get("wiki_stats", {})

    # --- Compiled file tracking ---

    def mark_compiled(self, compiled_path: str, raw_source: str):
        """Record a compiled file in the tracking list."""
        now = datetime.now(timezone.utc).isoformat()
        compiled_files = self._data.setdefault("compiled_files", [])
        compiled_files.append({
            "path": compiled_path,
            "raw_source": raw_source,
            "compiled_at": now,
            "status": "pending",
        })
        self.save()

    def get_pending_compiled(self) -> list[dict]:
        """Return compiled files with status='pending'."""
        compiled_files = self._data.get("compiled_files", [])
        return [e for e in compiled_files if e.get("status") == "pending"]

    def get_compiled_entry(self, compiled_path: str) -> Optional[dict]:
        """Find a compiled file entry by path."""
        for entry in self._data.get("compiled_files", []):
            if entry["path"] == compiled_path:
                return entry
        return None

    def mark_promoted(self, compiled_path: str):
        """Mark a compiled file as promoted."""
        for entry in self._data.get("compiled_files", []):
            if entry["path"] == compiled_path:
                entry["status"] = "promoted"
                entry["promoted_at"] = datetime.now(timezone.utc).isoformat()
                break
        stats = self._data.setdefault("wiki_stats", {})
        stats["promoted_count"] = stats.get("promoted_count", 0) + 1
        self.save()

    def mark_rejected(self, compiled_path: str, reason: str = ""):
        """Mark a compiled file as rejected."""
        for entry in self._data.get("compiled_files", []):
            if entry["path"] == compiled_path:
                entry["status"] = "rejected"
                entry["rejected_at"] = datetime.now(timezone.utc).isoformat()
                entry["reject_reason"] = reason
                break
        stats = self._data.setdefault("wiki_stats", {})
        stats["rejected_count"] = stats.get("rejected_count", 0) + 1
        self.save()
