"""
Prometheus — Android APK builder (Qt for Python / shiboken6)
=============================================================
Builds the SAME app as desktop — main.py, core/ and ui/ — into an APK with
pyside6-android-deploy. There is no separate Android UI to keep in step:
a change on desktop is a change on Android. The narrow-screen layout
switches on automatically (core/platform_info.py → PHONE_LAYOUT).

Needs (Linux or macOS; on Windows use WSL2 or the GitHub build):
  - PySide6 + shiboken6 Android wheels for your target, e.g.
      PySide6-6.x.y-6.x.y-cp311-cp311-android_aarch64.whl
      shiboken6-6.x.y-6.x.y-cp311-cp311-android_aarch64.whl
    Same version as the PySide6 installed on this computer.
  - JDK 17
  - Android NDK/SDK — downloaded by the deploy tool if not given

Usage:
  python build_apk.py --setup                      # install the deploy tool's needs
  python build_apk.py --debug                      # build a debug APK (finds wheels)
  python build_apk.py --debug --wheels ~/qtwheels  # say where the wheels are
  python build_apk.py --install                    # push the newest APK via ADB
  python build_apk.py --github                     # write a GitHub Actions workflow
  python build_apk.py --debug --dry-run            # show what would run

On the phone: run Ollama on a computer on the same WiFi, then set
⚙ Settings → Ollama URL to e.g. http://192.168.1.100:11434
"""

import argparse
import logging
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

APP_NAME = "Prometheus"
ROOT     = Path(__file__).resolve().parent

# Where to look for the Android wheels if --wheels isn't given
WHEEL_SEARCH_DIRS = [
    os.environ.get("PROMETHEUS_WHEELS", ""),
    ROOT / "wheels",
    Path.home() / "wheels",
    Path.home() / "qtwheels",
    Path.home() / "Downloads",
    Path.home() / ".pyside6_android_deploy",
]

# ── Additions to the buildozer config the deploy tool generates ────────────
# The tool only packs .py/.qml/.js/images and only PySide6 + shiboken6.
# Prometheus also needs its knowledge files, stylesheet and pure-Python deps.

EXTRA_INCLUDE_EXTS = ["md", "txt", "json", "qss"]

EXTRA_REQUIREMENTS = [
    "requests", "urllib3", "idna", "certifi", "charset-normalizer",   # Ollama client
    "sqlite3",                                                        # offline map search
]

EXTRA_PERMISSIONS = [
    "android.permission.INTERNET",                   # Ollama on the local network
    "android.permission.ACCESS_NETWORK_STATE",
    "android.permission.ACCESS_WIFI_STATE",
    "android.permission.CHANGE_WIFI_MULTICAST_STATE",  # peer discovery (UDP broadcast)
]

# Never packed: personal data, build output, dev-only folders
EXCLUDE_DIRS = [
    "memory", "voices", "tests", "bin", "build", "dist", "wheels",
    ".github", ".buildozer", "deployment", "prometheus_setup", "__pycache__",
]


# ── Step 1: checks ─────────────────────────────────────────────────────────

def check_platform():
    if platform.system() == "Windows":
        print("Android builds need Linux or macOS.\n"
              "  Option 1: run this inside WSL2 (Ubuntu)\n"
              "  Option 2: python build_apk.py --github   (builds on GitHub, free)")
        sys.exit(1)


def deploy_scripts_dir() -> Path:
    """Folder that holds pyside6-android-deploy's code inside the PySide6 install."""
    try:
        import PySide6
    except ImportError:
        print("PySide6 is not installed on this computer: pip install PySide6")
        sys.exit(1)
    scripts = Path(PySide6.__file__).parent / "scripts"
    if not (scripts / "android_deploy.py").exists():
        print(f"pyside6-android-deploy not found in {scripts}. Update PySide6.")
        sys.exit(1)
    return scripts


def host_pyside_version() -> str:
    import PySide6
    return PySide6.__version__


def check_jdk():
    try:
        out = subprocess.run(["java", "-version"], capture_output=True, text=True)
        text = out.stderr + out.stdout
        m = re.search(r'version "(\d+)', text)
        if m and int(m.group(1)) >= 17:
            return
        print(f"JDK 17+ is needed. Found: {text.strip().splitlines()[0] if text.strip() else 'none'}")
    except FileNotFoundError:
        print("Java not found. Install JDK 17 (e.g. sudo apt install openjdk-17-jdk).")
    sys.exit(1)


# ── Step 2: find the wheels ────────────────────────────────────────────────

def wheel_version(path: Path) -> str:
    m = re.match(r"(?:PySide6|shiboken6)-([\d.]+)", path.name)
    return m.group(1) if m else ""


def find_wheels(search_dir, arch: str):
    """Return (pyside_wheel, shiboken_wheel) for the arch, newest version first."""
    dirs = [Path(search_dir).expanduser()] if search_dir else [Path(d).expanduser() for d in WHEEL_SEARCH_DIRS if d]
    pyside, shiboken = [], []
    for d in dirs:
        if d.is_dir():
            pyside   += d.rglob(f"PySide6-*android*{arch}*.whl")
            shiboken += d.rglob(f"shiboken6-*android*{arch}*.whl")

    def newest(found):
        return max(found, key=lambda p: [int(x) for x in wheel_version(p).split(".") if x.isdigit()],
                   default=None)

    return newest(pyside), newest(shiboken)


# ── Step 3: build ──────────────────────────────────────────────────────────

def _patch_buildozer_config(scripts: Path):
    """
    The deploy tool deletes and regenerates buildozer.spec on every run, so the
    extras above are added by wrapping its config class instead of editing a file.
    """
    sys.path.insert(0, str(scripts))
    from deploy_lib.android import buildozer as bz

    Base = bz.BuildozerConfig

    class PrometheusBuildozerConfig(Base):
        def __init__(self, spec_file, pysidedeploy_config):
            super().__init__(spec_file, pysidedeploy_config)

            def merge(key, extra, sep=","):
                current = [x.strip() for x in (self.get_value("app", key, ignore_fail=True) or "").split(sep) if x.strip()]
                for item in extra:
                    if item not in current:
                        current.append(item)
                self.set_value("app", key, sep.join(current), raise_warning=False)

            merge("source.include_exts", EXTRA_INCLUDE_EXTS)
            merge("requirements", EXTRA_REQUIREMENTS)
            merge("android.permissions", EXTRA_PERMISSIONS, sep=", ")
            merge("source.exclude_dirs", EXCLUDE_DIRS)
            self.set_value("app", "title", APP_NAME, raise_warning=False)
            self.set_value("app", "orientation", "portrait", raise_warning=False)
            self.update_config()

    bz.BuildozerConfig = PrometheusBuildozerConfig


def build_apk(args):
    check_platform()
    scripts = deploy_scripts_dir()
    if not args.dry_run:
        check_jdk()

    # Find wheels
    pyside = Path(args.wheel_pyside) if args.wheel_pyside else None
    shiboken = Path(args.wheel_shiboken) if args.wheel_shiboken else None
    if not (pyside and shiboken):
        found_p, found_s = find_wheels(args.wheels, args.arch)
        pyside, shiboken = pyside or found_p, shiboken or found_s
    if not (pyside and shiboken and pyside.exists() and shiboken.exists()):
        print(f"Couldn't find PySide6 and shiboken6 Android wheels for {args.arch}.\n"
              "Give the folder with --wheels DIR, or each file with\n"
              "--wheel-pyside FILE --wheel-shiboken FILE.")
        sys.exit(1)
    print(f"PySide6 wheel:   {pyside}")
    print(f"shiboken6 wheel: {shiboken}")

    # The deploy tool must be the same version as the wheels
    host = host_pyside_version()
    if wheel_version(pyside) and not host.startswith(wheel_version(pyside)):
        print(f"\n⚠ Wheels are {wheel_version(pyside)} but this computer has PySide6 {host}.\n"
              f"  Install the matching version first:  pip install PySide6=={wheel_version(pyside)}\n")
        if not args.force:
            sys.exit(1)

    # Run the deploy tool in-process, from the project root (it needs main.py there)
    _patch_buildozer_config(scripts)
    from android_deploy import main as deploy_main

    os.chdir(ROOT)
    deploy_main(
        name=APP_NAME,
        pyside_wheel=pyside.resolve(),
        shiboken_wheel=shiboken.resolve(),
        ndk_path=Path(args.ndk).expanduser().resolve() if args.ndk else None,
        sdk_path=Path(args.sdk).expanduser().resolve() if args.sdk else None,
        config_file=None,
        init=False,
        loglevel=logging.INFO if args.verbose else logging.WARNING,
        dry_run=args.dry_run,
        keep_deployment_files=args.keep,
        force=True,
        extra_ignore_dirs=",".join(EXCLUDE_DIRS),
        extra_modules_grouped=None,
        no_install=args.no_install,
    )

    apks = sorted(ROOT.glob("*.apk"), key=lambda p: p.stat().st_mtime)
    if apks:
        apk = apks[-1]
        print(f"\n✅ APK built: {apk}  ({apk.stat().st_size / 1024 / 1024:.0f} MB)\n"
              f"Install: python build_apk.py --install   (or: adb install {apk.name})")
    elif not args.dry_run:
        print("\n✗ No APK found. Re-run with --verbose to see the build output.")


# ── Install and CI ─────────────────────────────────────────────────────────

def install_to_device():
    apks = sorted(ROOT.glob("*.apk"), key=lambda p: p.stat().st_mtime)
    if not apks:
        print("No APK found. Build first: python build_apk.py --debug")
        sys.exit(1)
    print(f"Installing {apks[-1].name} …")
    subprocess.run(["adb", "install", "-r", str(apks[-1])], check=False)


GITHUB_WORKFLOW = """name: Build Prometheus APK

# Builds the same PySide6 app as desktop for Android.
# Set two repository variables (Settings → Secrets and variables → Actions → Variables):
#   PYSIDE_ANDROID_WHEEL_URL    direct link to PySide6-…-android_aarch64.whl
#   SHIBOKEN_ANDROID_WHEEL_URL  direct link to shiboken6-…-android_aarch64.whl

on:
  workflow_dispatch:

jobs:
  build-apk:
    runs-on: ubuntu-24.04
    steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - uses: actions/setup-java@v4
      with:
        distribution: temurin
        java-version: '17'

    - name: Download Android wheels
      run: |
        mkdir -p wheels
        curl -fL -o "wheels/$(basename "${{ vars.PYSIDE_ANDROID_WHEEL_URL }}")" "${{ vars.PYSIDE_ANDROID_WHEEL_URL }}"
        curl -fL -o "wheels/$(basename "${{ vars.SHIBOKEN_ANDROID_WHEEL_URL }}")" "${{ vars.SHIBOKEN_ANDROID_WHEEL_URL }}"

    - name: Install matching PySide6 and the deploy tool
      run: |
        VERSION=$(ls wheels/PySide6-*.whl | sed -E 's/.*PySide6-([0-9.]+)-.*/\\1/')
        pip install "PySide6==$VERSION"
        python build_apk.py --setup

    - name: Build APK
      run: python build_apk.py --debug --wheels wheels --verbose

    - uses: actions/upload-artifact@v4
      with:
        name: Prometheus-APK
        path: "*.apk"
        retention-days: 30
"""


def generate_github_actions():
    path = ROOT / ".github" / "workflows" / "build_apk.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(GITHUB_WORKFLOW)
    print(f"✓ Created {path.relative_to(ROOT)}\n"
          "  Set PYSIDE_ANDROID_WHEEL_URL and SHIBOKEN_ANDROID_WHEEL_URL as repository variables,\n"
          "  push, then Actions → Build Prometheus APK → Run workflow.")


def setup():
    check_platform()
    scripts = deploy_scripts_dir()
    req = scripts / "requirements-android.txt"
    print("Installing the deploy tool's requirements …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req)], check=True)
    print("✓ Ready. Next: python build_apk.py --debug --wheels <folder with the Android wheels>")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Build the Prometheus Android APK (PySide6)")
    p.add_argument("--setup", action="store_true", help="install the deploy tool's requirements")
    p.add_argument("--debug", action="store_true", help="build a debug APK")
    p.add_argument("--install", action="store_true", help="install the newest APK via ADB")
    p.add_argument("--github", action="store_true", help="write a GitHub Actions workflow")
    p.add_argument("--wheels", help="folder containing the PySide6/shiboken6 Android wheels")
    p.add_argument("--wheel-pyside", help="PySide6 Android wheel file")
    p.add_argument("--wheel-shiboken", help="shiboken6 Android wheel file")
    p.add_argument("--arch", default="aarch64", choices=["aarch64", "x86_64"],
                   help="phone CPU (aarch64 for real phones, x86_64 for emulators)")
    p.add_argument("--ndk", help="Android NDK path (r28c)")
    p.add_argument("--sdk", help="Android SDK path")
    p.add_argument("--dry-run", action="store_true", help="show the commands without running them")
    p.add_argument("--keep", action="store_true", help="keep the generated build files")
    p.add_argument("--no-install", action="store_true",
                   help="don't let the deploy tool pip-install its own build tools")
    p.add_argument("--force", action="store_true", help="build even if wheel and PySide6 versions differ")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.setup:
        setup()
    elif args.github:
        generate_github_actions()
    elif args.install:
        install_to_device()
    elif args.debug:
        build_apk(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
