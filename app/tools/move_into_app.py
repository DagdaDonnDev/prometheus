"""
Tidies the prometheus folder into the new layout — run once after unzipping:

    prometheus/
    ├── Prometheus.exe     double-click to start
    ├── prometheus.sh      the same on Linux / macOS
    ├── README.md
    └── app/               everything else

    python app\\tools\\move_into_app.py            (from the prometheus folder)
    python app\\tools\\move_into_app.py --check    (only list what it would do)

Step 1: everything at the top that belongs in app/ is moved into it —
        models, ollama, runtime, piper, voices, memory, your books in
        knowledge_base, logs … Moving within one drive is instant, even for GB.
Step 2: where app/ already has the same file (the new code from the zip),
        the old copy at the top is deleted — the zip's one is newer
Step 3: old leftovers go: Prometheus.bat (Prometheus.exe replaces it), __pycache__
Left where they are: .git, a virtual environment (.venv / venv — moving one
breaks it), prometheus_setup (found there as before).
Then in git: `git add -A` records it all as moves.
"""

import os
import shutil
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent          # tools/ → app/
TOP = APP.parent

STAY = {".git", ".gitignore", "app", "Prometheus.exe", "prometheus.sh", "README.md", "CLAUDE.md",
        ".gitattributes", ".venv", "venv", "env", "prometheus_setup", ".idea", ".vscode"}
DROP = {"Prometheus.bat", "__pycache__"}


def _remove(path: Path, log: list) -> bool:
    try:
        shutil.rmtree(path) if path.is_dir() else path.unlink()
        return True
    except OSError:
        log.append(f"in use  {path.relative_to(TOP)}  (couldn't delete — still at the top)")
        return False


def merge(src: Path, dst: Path, check: bool, log: list):
    """Steps 1–2 for one entry: move it, or fold it into what's already in app/."""
    if not dst.exists() and not dst.is_symlink():
        if check:
            log.append(f"move    {src.relative_to(TOP)}  →  app/")
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(src, dst)
            log.append(f"move    {src.relative_to(TOP)}  →  app/")
            return
        except OSError:
            # Windows won't move a folder while something has a file in it open
            # (Prometheus, an Explorer window, an editor, a virus scan) — move
            # what's inside one by one instead, and list what's still in use
            if not src.is_dir():
                log.append(f"in use  {src.relative_to(TOP)}  (couldn't move — still at the top)")
                return
            dst.mkdir(exist_ok=True)
    if src.is_dir() and dst.is_dir():
        for child in sorted(src.iterdir()):
            merge(child, dst / child.name, check, log)
        if not check:
            try:
                src.rmdir()             # empty now
            except OSError:
                pass
        return
    # The same file in both places: app/ has the new one
    log.append(f"delete  {src.relative_to(TOP)}  (app/ has the new one)")
    if not check:
        _remove(src, log)


def main() -> int:
    check = "--check" in sys.argv
    if not (APP / "main.py").exists():
        print(f"[X] {APP} has no main.py — unzip the update first")
        return 1
    log = []
    for entry in sorted(TOP.iterdir()):
        name = entry.name
        if name in STAY:
            continue
        if name in DROP:                                        # Step 3
            log.append(f"delete  {name}  (no longer used)")
            if not check:
                _remove(entry, log)
            continue
        merge(entry, APP / name, check, log)
    if not log:
        print("[OK] Already tidy — nothing to move.")
        return 0
    stuck = [line for line in log if line.startswith("in use")]
    moved = sum(1 for line in log if line.startswith("move"))
    dropped = sum(1 for line in log if line.startswith("delete"))
    shown = [line for line in log if not line.startswith("in use")]
    for line in shown if (check or len(shown) <= 60) else shown[:60] + [f"… and {len(shown) - 60} more"]:
        print("  " + line)
    print(("\nWould move" if check else "\n[OK] Moved") + f" {moved}, "
          + ("would delete" if check else "deleted") + f" {dropped} old cop{'y' if dropped == 1 else 'ies'}.")
    if stuck:
        print(f"\n[!] {len(stuck)} file(s) are in use, so they stayed at the top:")
        for line in stuck[:20]:
            print("  " + line)
        print("Close Prometheus (and any window or editor showing these), then run this again —\n"
              "it carries on from where it stopped.")
        return 1
    if not check:
        print("Start Prometheus with Prometheus.exe. In git: git add -A")
    return 0


if __name__ == "__main__":
    sys.exit(main())
