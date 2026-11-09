"""
tools/build_exe.py
============
Builds Prometheus into a single executable for Windows, Linux, or macOS.

Usage:
    python tools/build_exe.py                  # build for current platform
    python tools/build_exe.py --onefile        # single .exe file (slower startup)
    python tools/build_exe.py --onedir         # folder with exe (faster startup)
    python tools/build_exe.py --clean          # clean build artifacts first

Output:
    dist/Prometheus.exe    (Windows)
    dist/Prometheus        (Linux/macOS)

Requirements:
    pip install pyinstaller

Notes:
    - The knowledge_base/, voices/, and memory/ folders are NOT bundled
      into the exe. They sit alongside it on disk. This is intentional:
      users can update knowledge without rebuilding.
    - Ollama runs as a separate process — not bundled. Users install it once.
    - The exe bundles: Python runtime, all dependencies, UI, core logic.
    - Size: approximately 150-300MB depending on platform.
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path

# Run from anywhere: work in the prometheus folder (one up from tools/) so
# relative paths and `import core…` resolve the same as for main.py
ROOT_DIR = Path(__file__).resolve().parent.parent
os.chdir(ROOT_DIR)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


# ── Build Configuration ────────────────────────────────────────────────────

APP_NAME        = "Prometheus"
APP_VERSION     = "1.0.0"
MAIN_SCRIPT     = "main.py"
ICON_WINDOWS    = "assets/icon.ico"
ICON_MAC        = "assets/icon.icns"
ICON_LINUX      = "assets/icon.png"

# Folders to copy alongside the executable (not bundled inside)
EXTERNAL_DIRS = [
    "knowledge_base",
    "voices",
]

# Files to copy alongside the executable
EXTERNAL_FILES = [
    "requirements.txt",
    "README.md",
]

# Hidden imports PyInstaller might miss
HIDDEN_IMPORTS = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
    "chromadb",
    "chromadb.api",
    "chromadb.db.impl",
    "chromadb.segment",
    "chromadb.segment.impl",
    "chromadb.telemetry",
    "sentence_transformers",
    "faster_whisper",
    "sounddevice",
    "numpy",
    "requests",
    "json",
    "pathlib",
]

# Data files to bundle inside the exe
DATAS = [
    ("assets/icon.png", "assets"),
    ("ui/style.qss", "ui"),
    # The code itself (core/, ui/ and their sub-folders) is collected by
    # PyInstaller from the imports — only non-Python files are listed here
]


# ── Platform Detection ─────────────────────────────────────────────────────

PLATFORM = platform.system()  # "Windows", "Linux", "Darwin"

def get_icon():
    if PLATFORM == "Windows" and Path(ICON_WINDOWS).exists():
        return ICON_WINDOWS
    elif PLATFORM == "Darwin" and Path(ICON_MAC).exists():
        return ICON_MAC
    elif Path(ICON_LINUX).exists():
        return ICON_LINUX
    return None

def get_exe_name():
    if PLATFORM == "Windows":
        return f"{APP_NAME}.exe"
    return APP_NAME

def get_separator():
    return ";" if PLATFORM == "Windows" else ":"


# ── Build Functions ────────────────────────────────────────────────────────

def check_pyinstaller():
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__} found")
        return True
    except ImportError:
        print("PyInstaller not found. Installing...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✓ PyInstaller installed")
            return True
        else:
            print(f"✗ Failed to install PyInstaller: {result.stderr}")
            return False


def clean_build():
    print("Cleaning previous build artifacts...")
    for d in ["build", "dist", "__pycache__"]:
        if Path(d).exists():
            shutil.rmtree(d)
            print(f"  Removed {d}/")
    for spec in Path(".").glob("*.spec"):
        spec.unlink()
        print(f"  Removed {spec}")


def create_assets():
    """
    Make the platform icon files from assets/icon.png (the one to edit).

    Step 1: no icon.png → nothing to do (the build uses no icon)
    Step 2: icon.ico (Windows, several sizes) and icon.icns (macOS) from it,
            whenever icon.png is newer
    """
    png = Path(ICON_LINUX)
    if not png.exists():
        print("  (no assets/icon.png — building without an icon)")
        return
    try:
        from PIL import Image
    except ImportError:
        print("  (pip install pillow to turn assets/icon.png into .ico/.icns)")
        return
    img = Image.open(png).convert("RGBA")
    for target, kwargs in ((Path(ICON_WINDOWS), {"sizes": [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]}),
                           (Path(ICON_MAC), {})):
        if target.exists() and target.stat().st_mtime >= png.stat().st_mtime:
            continue
        try:
            img.save(target, **kwargs)
            print(f"  ✓ {target}")
        except Exception as e:
            print(f"  (couldn't write {target}: {e})")


def build_spec(onefile: bool = True) -> str:
    """Generate PyInstaller spec file content."""

    sep = get_separator()

    # Build datas list
    datas_str = ",\n        ".join(
        f'("{src}", "{dst}")'
        for src, dst in DATAS
        if Path(src.split("*")[0]).exists()
    )

    # Build hidden imports list
    hidden_str = ",\n        ".join(f'"{h}"' for h in HIDDEN_IMPORTS)

    icon = get_icon()
    icon_str = f'icon="{icon}"' if icon else "icon=None"

    if onefile:
        exe_type = "EXE"
        collect = ""
        analysis_extra = ""
    else:
        exe_type = "EXE"
        collect = """
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='{name}',
)""".format(name=APP_NAME)
        analysis_extra = ""

    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-
# Prometheus PyInstaller spec file
# Generated by tools/build_exe.py

block_cipher = None

a = Analysis(
    ['{MAIN_SCRIPT}'],
    pathex=['.'],
    binaries=[],
    datas=[
        {datas_str}
    ],
    hiddenimports=[
        {hidden_str}
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'PIL',
        'cv2',
        'tensorflow',
        'torch',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    {'a.binaries, a.zipfiles, a.datas,' if onefile else '[]'},
    exclude_binaries={'False' if onefile else 'True'},
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    {icon_str},
)
{collect if not onefile else ''}
"""
    return spec_content


def run_pyinstaller(onefile: bool = True):
    """Run PyInstaller with appropriate arguments."""
    sep = get_separator()
    icon = get_icon()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",           # No console window
        "--noconfirm",          # Overwrite without asking
        "--clean",              # Clean cache
    ]

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    if icon:
        cmd.extend(["--icon", icon])

    # Add hidden imports
    for imp in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", imp])

    # Add data files
    for src, dst in DATAS:
        if Path(src.split("*")[0]).exists():
            cmd.extend(["--add-data", f"{src}{sep}{dst}"])

    # Exclude unnecessary modules
    for exc in ["tkinter", "matplotlib", "scipy", "pandas"]:
        cmd.extend(["--exclude-module", exc])

    cmd.append(MAIN_SCRIPT)

    print(f"\nRunning PyInstaller...")
    print(f"Command: {' '.join(cmd[:6])} ...")

    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def copy_external_assets():
    """Copy knowledge_base, voices etc alongside the built exe."""
    dist_dir = Path("dist")

    if not dist_dir.exists():
        return

    # For onedir builds, copy into the app directory
    app_dir = dist_dir / APP_NAME
    target = app_dir if app_dir.exists() else dist_dir

    print(f"\nCopying external assets to {target}...")

    for d in EXTERNAL_DIRS:
        src = Path(d)
        if src.exists():
            dst = target / d
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"  ✓ {d}/")
        else:
            # Create empty directory with README
            dst = target / d
            dst.mkdir(parents=True, exist_ok=True)
            (dst / "README.txt").write_text(
                f"Place {d} contents here.\n"
                f"See README.md for details.\n"
            )
            print(f"  ✓ {d}/ (empty — add contents)")

    for f in EXTERNAL_FILES:
        src = Path(f)
        if src.exists():
            shutil.copy2(src, target / f)
            print(f"  ✓ {f}")

    # Create empty memory directory
    (target / "memory").mkdir(exist_ok=True)
    (target / "voices").mkdir(exist_ok=True)

    # Write launcher instructions
    instructions = target / "SETUP.txt"
    instructions.write_text(f"""
PROMETHEUS SETUP
================

1. Install Ollama from: https://ollama.ai
   Then run: ollama pull hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF

2. Download source materials:
   Copy tools/bootstrap.py into this folder and run:
   python tools/bootstrap.py

3. Index knowledge base:
   python tools/ingest.py

4. Launch Prometheus:
   {get_exe_name()}

Note: Prometheus runs completely offline after initial setup.
Ollama must be running in the background (it auto-starts on most systems).

For voice support:
   - TTS: Download Piper from https://github.com/rhasspy/piper/releases
          Place piper executable and voice .onnx files in voices/ folder
   - STT: pip install faster-whisper sounddevice
""")
    print(f"  ✓ SETUP.txt")


def create_windows_installer():
    """
    Create a Windows NSIS installer script.
    Requires NSIS installed: https://nsis.sourceforge.io
    """
    nsis_script = f"""
; Prometheus Windows Installer
; Build with: makensis prometheus_installer.nsi

!define APP_NAME "{APP_NAME}"
!define APP_VERSION "{APP_VERSION}"
!define EXE_NAME "{APP_NAME}.exe"

Name "${{APP_NAME}} ${{APP_VERSION}}"
OutFile "Prometheus_Setup_${{APP_VERSION}}.exe"
InstallDir "$PROGRAMFILES\\${{APP_NAME}}"
InstallDirRegKey HKCU "Software\\${{APP_NAME}}" ""
RequestExecutionLevel admin

Section "Install"
    SetOutPath "$INSTDIR"
    File /r "dist\\{APP_NAME}\\*.*"

    ; Create desktop shortcut
    CreateShortcut "$DESKTOP\\${{APP_NAME}}.lnk" "$INSTDIR\\${{EXE_NAME}}"

    ; Create start menu entry
    CreateDirectory "$SMPROGRAMS\\${{APP_NAME}}"
    CreateShortcut "$SMPROGRAMS\\${{APP_NAME}}\\${{APP_NAME}}.lnk" "$INSTDIR\\${{EXE_NAME}}"

    ; Registry entry for uninstaller
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" \\
                "DisplayName" "${{APP_NAME}}"
    WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}" \\
                "UninstallString" "$INSTDIR\\Uninstall.exe"
    WriteUninstaller "$INSTDIR\\Uninstall.exe"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\\*.*"
    RMDir /r "$INSTDIR"
    Delete "$DESKTOP\\${{APP_NAME}}.lnk"
    RMDir /r "$SMPROGRAMS\\${{APP_NAME}}"
    DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${{APP_NAME}}"
SectionEnd
"""
    Path("prometheus_installer.nsi").write_text(nsis_script)
    print("✓ Created prometheus_installer.nsi")
    print("  Build installer with: makensis prometheus_installer.nsi")


def print_result(success: bool, onefile: bool):
    exe = get_exe_name()
    dist = Path("dist")

    if success:
        if onefile:
            exe_path = dist / exe
            size = exe_path.stat().st_size / 1024 / 1024 if exe_path.exists() else 0
            print(f"""
{'='*50}
✅ BUILD SUCCESSFUL
{'='*50}

Executable: dist/{exe}
Size:       {size:.0f} MB

To distribute:
  Copy the entire dist/ folder to the target machine.
  User also needs Ollama installed separately.
""")
        else:
            print(f"""
{'='*50}
✅ BUILD SUCCESSFUL
{'='*50}

App folder: dist/{APP_NAME}/
Executable: dist/{APP_NAME}/{exe}

To distribute:
  Zip the entire dist/{APP_NAME}/ folder.
  User also needs Ollama installed separately.
""")
    else:
        print(f"""
{'='*50}
✗ BUILD FAILED
{'='*50}

Check the output above for errors.
Common fixes:
  pip install pyinstaller --upgrade
  pip install PySide6 --upgrade
""")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build Prometheus into a standalone executable"
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        default=True,
        help="Build single executable file (default)"
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Build as folder with executable (faster startup)"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean previous build artifacts first"
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="Also generate Windows NSIS installer script"
    )
    args = parser.parse_args()

    onefile = not args.onedir

    print(f"""
{'='*50}
⚡ PROMETHEUS EXE BUILDER
{'='*50}
Platform:  {PLATFORM}
Mode:      {'Single file' if onefile else 'Directory'}
Output:    dist/{get_exe_name()}
{'='*50}
""")

    if args.clean:
        clean_build()

    if not check_pyinstaller():
        sys.exit(1)

    create_assets()

    success = run_pyinstaller(onefile=onefile)

    if success:
        copy_external_assets()

        if args.installer and PLATFORM == "Windows":
            create_windows_installer()

    print_result(success, onefile)


if __name__ == "__main__":
    main()
