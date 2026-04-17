"""wiki gc command - garbage collect stale raw/ and compiled/ files."""
from datetime import datetime, timezone, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ..core.compiler import _atomic_write
from ..core.config import Config
from ..core.state import WikiState

console = Console()


def gc_command(config: Config, dry_run: bool = False, force: bool = False):
    """Run garbage collection on raw/ and compiled/ files."""
    state = WikiState(config)

    archive_days = config.get("behavior.raw_archive_days", 90)
    delete_days = config.get("behavior.raw_delete_days", 180)

    # Collect actions
    to_archive = []  # raw/ files to move to archive
    to_delete = []   # archive/ files to delete
    to_auto_reject = []  # compiled/ drafts to auto-reject

    now = datetime.now(timezone.utc)

    # 1. Find raw/ files older than archive_days with no compiled output
    if config.raw_dir.exists():
        processed = state.get_processed_hashes()
        compiled_sources = set()
        for entry in state._data.get("compiled_files", []):
            raw_src = entry.get("raw_source", "")
            if raw_src:
                compiled_sources.add(raw_src)

        for f in sorted(config.raw_dir.rglob("*")):
            if not f.is_file():
                continue
            # Skip files already in archive/
            if "archive" in f.parts:
                continue

            # Check file age
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            except Exception:
                continue

            age_days = (now - mtime).days
            if age_days < archive_days:
                continue

            # Check if there's a compiled output for this raw file
            rel = str(f.relative_to(config.wiki_root))
            if rel in compiled_sources:
                continue

            to_archive.append(f)

    # 2. Find archive/ files older than delete_days
    archive_dir = config.raw_archive_dir
    if archive_dir.exists():
        for f in sorted(archive_dir.rglob("*")):
            if not f.is_file():
                continue
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            except Exception:
                continue

            age_days = (now - mtime).days
            if age_days >= delete_days:
                to_delete.append(f)

    # 3. Find compiled/ drafts pending for too long
    if config.compiled_dir.exists():
        for entry in state.get_pending_compiled():
            compiled_at_str = entry.get("compiled_at", "")
            if not compiled_at_str:
                continue
            try:
                compiled_at = datetime.fromisoformat(compiled_at_str.replace("Z", "+00:00"))
            except Exception:
                continue

            age_days = (now - compiled_at).days
            if age_days >= delete_days:
                compiled_path = config.wiki_root / entry["path"]
                if compiled_path.exists():
                    to_auto_reject.append((compiled_path, age_days))

    # Display summary
    total_actions = len(to_archive) + len(to_delete) + len(to_auto_reject)

    if total_actions == 0:
        console.print("[green]✓ Nothing to clean up.[/green]")
        return

    console.print(f"[bold]Garbage Collection Summary[/bold]\n")

    if to_archive:
        table = Table(title=f"Raw → Archive ({archive_days}+ days, no compiled output)", show_header=True)
        table.add_column("File", style="dim")
        table.add_column("Age", justify="right")
        for f in to_archive[:20]:
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                age = (now - mtime).days
            except Exception:
                age = "?"
            table.add_row(str(f.relative_to(config.wiki_root)), f"{age}d")
        if len(to_archive) > 20:
            table.add_row(f"... and {len(to_archive) - 20} more", "")
        console.print(table)

    if to_delete:
        table = Table(title=f"Archive → Delete ({delete_days}+ days)", show_header=True)
        table.add_column("File", style="dim")
        table.add_column("Age", justify="right")
        for f in to_delete[:20]:
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                age = (now - mtime).days
            except Exception:
                age = "?"
            table.add_row(str(f.relative_to(config.wiki_root)), f"{age}d")
        if len(to_delete) > 20:
            table.add_row(f"... and {len(to_delete) - 20} more", "")
        console.print(table)

    if to_auto_reject:
        table = Table(title=f"Compiled → Auto-reject (pending {delete_days}+ days)", show_header=True)
        table.add_column("File", style="dim")
        table.add_column("Pending", justify="right")
        for f, age in to_auto_reject[:20]:
            table.add_row(str(f.relative_to(config.wiki_root)), f"{age}d")
        if len(to_auto_reject) > 20:
            table.add_row(f"... and {len(to_auto_reject) - 20} more", "")
        console.print(table)

    if dry_run:
        console.print(f"\n[yellow]--dry-run: {total_actions} file(s) would be affected.[/yellow]")
        return

    if not force:
        confirmed = click.confirm(f"\nProceed with {total_actions} action(s)?", default=False)
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            return

    # Execute
    archived = 0
    deleted = 0
    rejected = 0

    # Archive raw files
    archive_dir.mkdir(parents=True, exist_ok=True)
    for f in to_archive:
        try:
            dest = archive_dir / f.relative_to(config.raw_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            f.rename(dest)
            archived += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] Failed to archive {f.name}: {e}")

    # Delete archived files
    for f in to_delete:
        try:
            f.unlink()
            deleted += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] Failed to delete {f.name}: {e}")

    # Auto-reject compiled drafts
    for f, age in to_auto_reject:
        try:
            _auto_reject_compiled(config, state, f, age)
            rejected += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] Failed to auto-reject {f.name}: {e}")

    console.print(
        f"\n[bold green]GC complete.[/bold green] "
        f"{archived} archived, {deleted} deleted, {rejected} auto-rejected."
    )

    state.update_last_gc()


def _auto_reject_compiled(config: Config, state: WikiState, compiled_path: Path, age_days: int):
    """Auto-reject a stale compiled draft and write feedback."""
    reason = f"审核超时（pending {age_days} 天），自动拒绝"

    # Write feedback
    from datetime import date
    today = date.today().isoformat()
    rel_path = str(compiled_path.relative_to(config.wiki_root))

    feedback_path = config.compile_feedback_file
    if feedback_path.exists():
        existing = feedback_path.read_text(encoding="utf-8")
    else:
        existing = (
            "# Compile 反馈记录\n"
            "# 此文件由 wiki promote --reject 自动追加，供 Compile 阶段参考\n"
        )

    entry = f"\n\n## {today} — {rel_path}\n- 原因：{reason}\n"
    _atomic_write(feedback_path, existing + entry)

    # Mark as rejected in state
    state.mark_rejected(rel_path, reason)

    # Delete the compiled file
    compiled_path.unlink()
    # Also clean up patch files
    patch_file = compiled_path.parent / f"patch-{compiled_path.stem}.json"
    if patch_file.exists():
        patch_file.unlink()
