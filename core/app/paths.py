"""
Project paths — one place that knows where things live on disk.

PROJECT_DIR   the folder with main.py
setup_dir()   prometheus_setup/ — downloads, Piper, dumps. It may sit inside
              the project or next to it (…/prometheus_setup beside …/prometheus);
              whichever exists is used, inside first.
"""

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent


def setup_dir() -> Path:
    inside = PROJECT_DIR / "prometheus_setup"
    beside = PROJECT_DIR.parent / "prometheus_setup"
    if inside.is_dir():
        return inside
    if beside.is_dir():
        return beside
    return inside   # default for new downloads
