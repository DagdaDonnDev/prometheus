"""
Automatic Backup System
========================
Silently backs up memory and tab history on every close.
Keeps last 30 daily backups.
Auto-restores if primary files are corrupted.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


MEMORY_DIR   = Path("memory")
BACKUP_DIR   = Path("memory/backups")
MAX_BACKUPS  = 30

# Files to back up
BACKUP_TARGETS = [
    "memory/user_memory.json",
    "memory/tabs.json",
    "memory/config.json",
    "memory/processed_sources.json",
    "memory/training/graph.json",      # Training Path learning (v22)
]


class BackupManager:

    def __init__(self):
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    def backup(self, label: Optional[str] = None) -> bool:
        """
        Back up all memory files.
        Called automatically on app close.
        Returns True if backup succeeded.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        tag = f"_{label}" if label else ""
        backup_folder = BACKUP_DIR / f"backup_{timestamp}{tag}"

        try:
            backup_folder.mkdir(parents=True, exist_ok=True)

            backed_up = 0
            for target in BACKUP_TARGETS:
                src = Path(target)
                if src.exists():
                    shutil.copy2(src, backup_folder / src.name)
                    backed_up += 1

            if backed_up == 0:
                backup_folder.rmdir()
                return False

            # Write backup manifest
            manifest = {
                "timestamp": timestamp,
                "label": label,
                "files": backed_up,
                "day": self._get_current_day(),
            }
            (backup_folder / "manifest.json").write_text(
                json.dumps(manifest, indent=2)
            )

            # Prune old backups
            self._prune()
            return True

        except Exception:
            return False

    def restore_latest(self) -> bool:
        """
        Restore from most recent backup.
        Called automatically if primary files fail to load.
        """
        backups = self._list_backups()
        if not backups:
            return False

        latest = backups[-1]

        try:
            for target in BACKUP_TARGETS:
                src_name = Path(target).name
                backup_file = latest / src_name
                if backup_file.exists():
                    Path(target).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_file, target)

            return True
        except Exception:
            return False

    def list_backups(self) -> list:
        """Return list of backup info dicts for display."""
        backups = self._list_backups()
        result = []

        for folder in reversed(backups):  # newest first
            manifest_path = folder / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                    result.append({
                        "folder": str(folder),
                        "timestamp": manifest.get("timestamp", "unknown"),
                        "day": manifest.get("day", "?"),
                        "label": manifest.get("label", ""),
                        "files": manifest.get("files", 0),
                    })
                except Exception:
                    pass

        return result

    def restore_from(self, folder_path: str) -> bool:
        """Restore from a specific backup folder."""
        folder = Path(folder_path)
        if not folder.exists():
            return False

        try:
            for target in BACKUP_TARGETS:
                src_name = Path(target).name
                backup_file = folder / src_name
                if backup_file.exists():
                    Path(target).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_file, target)
            return True
        except Exception:
            return False

    def verify_primary_files(self) -> tuple:
        """
        Check if primary files are valid JSON.
        Returns (all_ok: bool, broken_files: list)
        """
        broken = []
        for target in BACKUP_TARGETS:
            path = Path(target)
            if not path.exists():
                continue
            try:
                json.loads(path.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                broken.append(target)

        return len(broken) == 0, broken

    def _list_backups(self) -> list:
        """Return sorted list of backup folder paths."""
        if not BACKUP_DIR.exists():
            return []

        folders = [
            d for d in BACKUP_DIR.iterdir()
            if d.is_dir() and d.name.startswith("backup_")
        ]
        return sorted(folders)

    def _prune(self):
        """Remove oldest backups beyond MAX_BACKUPS."""
        backups = self._list_backups()
        while len(backups) > MAX_BACKUPS:
            oldest = backups.pop(0)
            try:
                shutil.rmtree(oldest)
            except Exception:
                pass

    def _get_current_day(self) -> int:
        """Read current day from memory file."""
        try:
            memory_path = Path("memory/user_memory.json")
            if memory_path.exists():
                data = json.loads(memory_path.read_text())
                return data.get("user", {}).get("day_count", 1)
        except Exception:
            pass
        return 1

    def get_backup_size_mb(self) -> float:
        """Total size of all backups in MB."""
        if not BACKUP_DIR.exists():
            return 0.0
        total = sum(
            f.stat().st_size
            for f in BACKUP_DIR.rglob("*")
            if f.is_file()
        )
        return total / 1024 / 1024
