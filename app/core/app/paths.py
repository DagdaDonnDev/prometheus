"""
Project paths — one place that knows where things live on disk.

PROJECT_DIR   the folder with main.py
setup_dir()   prometheus_setup/ — downloads, Piper, dumps. It may sit inside
              app/, next to it, or next to the prometheus folder that holds
              Prometheus.exe and app/ (…/prometheus_setup beside …/prometheus);
              whichever exists is used, inside first.
"""

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent


def setup_dir() -> Path:
    inside = PROJECT_DIR / "prometheus_setup"
    for place in (inside, PROJECT_DIR.parent / "prometheus_setup",
                  PROJECT_DIR.parent.parent / "prometheus_setup"):
        if place.is_dir():
            return place
    return inside   # default for new downloads
