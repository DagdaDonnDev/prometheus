"""
Builds Prometheus.exe — the double-click way to start Prometheus on Windows.

    python tools/build_exe.py            (from the app folder)

It's a small launcher (tools/launcher/prometheus_launcher.c) with your icon
(assets/icon.png), placed next to the app folder:

    prometheus/
    ├── Prometheus.exe     ← double-click this
    └── app/               ← everything else (code, models, books, Python…)

Why not the whole app frozen into one .exe: a one-file exe unpacks itself
on every start — with the AI models and library that's ~10 GB each time, and
past ~4 GB it doesn't work at all. The launcher starts the app in place
instead, so it opens as fast as `python main.py` and stays easy to update.

Prometheus.exe is committed, so you only need this after changing the
launcher or the icon.

Step 1: assets/icon.png → assets/icon.ico (all the sizes Windows uses; Pillow)
Step 2: compile the launcher with MinGW-w64 (Windows: MSYS2 / w64devkit;
        Linux: the gcc-mingw-w64-x86-64 package) with the icon and file details
Step 3: put it next to the app folder
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Run from anywhere: work in the app folder (one up from tools/)
ROOT_DIR = Path(__file__).resolve().parent.parent
os.chdir(ROOT_DIR)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

LAUNCHER = ROOT_DIR / "tools" / "launcher"
ICON_PNG = ROOT_DIR / "assets" / "icon.png"
ICON_ICO = ROOT_DIR / "assets" / "icon.ico"
OUT = ROOT_DIR.parent / "Prometheus.exe"
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def make_icon() -> bool:
    """Step 1."""
    try:
        from PIL import Image
    except ImportError:
        print("[!] pip install pillow — needed to turn assets/icon.png into an .ico")
        return False
    img = Image.open(ICON_PNG).convert("RGBA")
    side = max(img.size)                       # square it without stretching
    if img.size[0] != img.size[1]:
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(img, ((side - img.size[0]) // 2, (side - img.size[1]) // 2))
        img = square
    img.save(ICON_ICO, sizes=[(s, s) for s in SIZES])
    print(f"[OK] {ICON_ICO.relative_to(ROOT_DIR)} ({len(SIZES)} sizes)")
    return True


def _tool(*names):
    return next((shutil.which(n) for n in names if shutil.which(n)), None)


def compile_launcher() -> bool:
    """Steps 2–3."""
    gcc = _tool("x86_64-w64-mingw32-gcc", "gcc" if os.name == "nt" else "")
    windres = _tool("x86_64-w64-mingw32-windres", "windres" if os.name == "nt" else "")
    if not gcc or not windres:
        print("[!] MinGW-w64 isn't installed, so the launcher can't be rebuilt here.\n"
              "    Windows: install w64devkit or MSYS2 (mingw-w64-x86_64-gcc)\n"
              "    Linux:   sudo apt install gcc-mingw-w64-x86-64\n"
              "    The committed Prometheus.exe still works.")
        return False
    build = LAUNCHER / "build"
    build.mkdir(exist_ok=True)
    shutil.copy2(ICON_ICO, build / "icon.ico")
    shutil.copy2(LAUNCHER / "prometheus.rc", build / "prometheus.rc")
    res = build / "prometheus_res.o"
    steps = [
        [windres, str(build / "prometheus.rc"), "-O", "coff", "-o", str(res)],
        [gcc, "-Os", "-s", "-municode", "-mwindows", "-static",
         str(LAUNCHER / "prometheus_launcher.c"), str(res), "-o", str(OUT), "-lshell32"],
    ]
    for cmd in steps:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print("[X] " + " ".join(Path(c).name for c in cmd[:2]) + " failed:\n" + r.stderr)
            return False
    shutil.rmtree(build, ignore_errors=True)
    print(f"[OK] {OUT} ({OUT.stat().st_size // 1024} KB)")
    return True


def main():
    if not ICON_PNG.exists():
        print("[X] assets/icon.png is missing")
        sys.exit(1)
    if not make_icon():
        sys.exit(1)
    sys.exit(0 if compile_launcher() else 1)


if __name__ == "__main__":
    main()
