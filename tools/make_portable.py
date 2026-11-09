"""
Make the prometheus folder self-contained — copy it to another computer
(same kind: Windows → Windows) and it runs, with nothing to install.

    python tools/make_portable.py            gather everything into the folder
    python tools/make_portable.py --check    only list what's still outside (changes nothing)

Step 1  AI models      both models (speaker + librarian) → prometheus/models
                       (moved from Ollama's usual folder; nothing re-downloaded)
Step 2  Ollama         the Ollama program → prometheus/ollama
                       (Prometheus uses this copy first; your installed one is untouched)
Step 3  Voice          Piper → prometheus/piper; the Whisper model → prometheus/models/whisper
Step 4  Python         Windows: Python's official portable build → prometheus/runtime/python,
                       with every package Prometheus needs installed into it (needs
                       internet this once). Other systems: the packages are saved to
                       prometheus/wheels so a new machine can install them offline.
Step 5  Launchers      Prometheus.bat / prometheus.sh start it with the copies above
Step 6  Report         folder size, and anything still outside (an Obsidian vault, say)

Your chats, memory, settings, library and its search index are already inside
(memory/ and knowledge_base/) and use paths relative to the folder.
"""

import io
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # tools/ → the prometheus folder
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

RUNTIME = ROOT / "runtime" / "python"
OLLAMA_DIR = ROOT / "ollama"
PIPER_DIR = ROOT / "piper"
WHEELS = ROOT / "wheels"
# Python's last 3.12 release with a portable (embeddable) build — used if this
# computer's exact version has none
FALLBACK_PYTHON = "3.12.10"


def ok(m):   print(f"[OK] {m}")
def info(m): print(f"[..] {m}")
def warn(m): print(f"[!]  {m}")
def bad(m):  print(f"[X]  {m}")


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def _gb(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def _inside(path) -> bool:
    try:
        Path(path).resolve().relative_to(ROOT)
        return True
    except ValueError:
        return False


# ── Step 1 ──────────────────────────────────────────────────────────────────

def step_models(check: bool) -> bool:
    from core.ai import ollama_local as ol
    names = ol._configured_models()
    all_ok = True
    for name in names:
        if ol._find_manifest(ol.MODELS_DIR, name):
            ok(f"model {name} is in prometheus/models")
            continue
        if check:
            where = ol._find_manifest(ol.default_store(), name)
            (warn if where else bad)(f"model {name} is " + (f"outside: {ol.default_store()}" if where
                                                          else "not downloaded"))
            all_ok = False
            continue
        if not ol.move_model(name, dst=ol.MODELS_DIR):
            bad(f"{name} isn't downloaded yet — get it with:  python -m core.ai.ollama_local --pull {name}")
            all_ok = False
    return all_ok


# ── Step 2 ──────────────────────────────────────────────────────────────────

def _ollama_install(exe: Path):
    """(folder to copy, where it goes) for an installed Ollama."""
    if os.name == "nt":
        return exe.parent, OLLAMA_DIR                    # …\\Programs\\Ollama → ollama\\
    if sys.platform == "darwin":
        return exe.parent, OLLAMA_DIR / "bin"            # app Resources → ollama/bin
    return None, None                                    # Linux: binary + ../lib/ollama, handled below


def step_ollama(check: bool) -> bool:
    from core.ai import ollama_local as ol
    exe = ol.find_ollama()
    if exe and _inside(exe):
        ok(f"Ollama is in the folder ({Path(exe).relative_to(ROOT)})")
        return True
    if not exe:
        bad("Ollama isn't installed here — install it (ollama.com/download), then run this again")
        return False
    if check:
        warn(f"Ollama is outside: {exe}")
        return False
    exe = Path(exe).resolve()
    src, dst = _ollama_install(exe)
    info(f"Copying Ollama from {exe.parent} (its GPU libraries make this a GB or two)…")
    if src is not None:
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        # Linux: /usr/local/bin/ollama with its libraries in /usr/local/lib/ollama
        (OLLAMA_DIR / "bin").mkdir(parents=True, exist_ok=True)
        shutil.copy2(exe, OLLAMA_DIR / "bin" / "ollama")
        libs = exe.parent.parent / "lib" / "ollama"
        if libs.is_dir():
            shutil.copytree(libs, OLLAMA_DIR / "lib" / "ollama", dirs_exist_ok=True)
    copied = ol.find_ollama()
    if not copied or not _inside(copied):
        bad("Copied, but Prometheus can't find Ollama in the folder")
        return False
    try:
        version = subprocess.run([copied, "--version"], capture_output=True, text=True,
                                 timeout=20).stdout.strip().splitlines()[-1:]
    except Exception:
        version = []
    ok(f"Ollama copied ({_gb(_size(OLLAMA_DIR))}){' — ' + version[0] if version else ''}")
    return True


# ── Step 3 ──────────────────────────────────────────────────────────────────

def step_voice(check: bool) -> bool:
    from core.voice.voice_manager import VoiceManager
    from core.app.config import Config
    good = True
    vm = VoiceManager()
    piper = vm.find_piper()
    if piper and _inside(piper):
        ok("Piper is in the folder")
    elif piper:
        if check:
            warn(f"Piper is outside: {piper}")
            good = False
        else:
            src = Path(piper).resolve().parent          # keep espeak-ng-data with it
            shutil.copytree(src, PIPER_DIR, dirs_exist_ok=True)
            ok(f"Piper copied into the folder ({_gb(_size(PIPER_DIR))})")
    else:
        warn("No Piper — voice output off. Set it up with:  python tools/setup_voice.py")

    size = Config.load().stt_model or "tiny"
    target = ROOT / "models" / "whisper" / size
    if (target / "model.bin").is_file():
        ok(f"Whisper '{size}' is in the folder")
        return good
    # Downloaded by an older version into a Hugging Face cache? Bring it in.
    caches = [ROOT / "memory" / "model_cache", ROOT / "models" / "whisper_cache",
              Path.home() / ".cache" / "huggingface" / "hub"]
    for cache in caches:
        for snap in cache.glob(f"models--Systran--faster-whisper-{size}/snapshots/*"):
            if (snap / "model.bin").exists():
                if check:
                    warn(f"Whisper '{size}' is in {cache}" + ("" if _inside(cache) else " (outside)"))
                    return False
                shutil.copytree(snap, target, dirs_exist_ok=True)
                ok(f"Whisper '{size}' copied into the folder")
                return good
    warn("No Whisper model yet — voice input off. Set it up with:  python tools/setup_voice.py")
    return good


# ── Step 4 ──────────────────────────────────────────────────────────────────

def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Prometheus-portable/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def enable_site_packages(python_dir: Path):
    """
    The portable build ignores installed packages until its ._pth file says
    otherwise: switch on `import site` and add Lib\\site-packages.
    """
    for pth in python_dir.glob("python*._pth"):
        lines = pth.read_text(encoding="utf-8").splitlines()
        lines = ["import site" if ln.strip() == "#import site" else ln for ln in lines]
        if "import site" not in lines:
            lines.append("import site")
        if not any(ln.strip().lower() == r"lib\site-packages" for ln in lines):
            lines.insert(0, r"Lib\site-packages")
        pth.write_text("\n".join(lines) + "\n", encoding="utf-8")


def step_python(check: bool) -> bool:
    exe = RUNTIME / "python.exe"
    if os.name != "nt":
        # A portable Python isn't standard outside Windows; keep the packages instead
        if WHEELS.is_dir() and any(WHEELS.iterdir()):
            ok(f"Packages saved in prometheus/wheels ({_gb(_size(WHEELS))})")
            return True
        if check:
            warn("Python packages aren't saved in the folder")
            return False
        info("Saving every package Prometheus needs into prometheus/wheels…")
        code = subprocess.call([sys.executable, "-m", "pip", "download", "-r", "requirements.txt",
                                "-d", str(WHEELS)])
        if code:
            bad("pip couldn't save the packages")
            return False
        ok("Packages saved. On the new machine:  python3 -m pip install --no-index "
           "--find-links wheels -r requirements.txt")
        return True

    if exe.exists():
        ok("Portable Python is in the folder (runtime\\python)")
        return True
    if check:
        warn("Python and its packages are outside the folder")
        return False

    # Step 4a: Python's portable build, the same version as this one if it has one
    arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "amd64"
    data = None
    for version in (platform.python_version(), FALLBACK_PYTHON):
        url = f"https://www.python.org/ftp/python/{version}/python-{version}-embed-{arch}.zip"
        try:
            info(f"Downloading portable Python {version}…")
            data = _download(url)
            break
        except Exception as e:
            warn(f"Not available ({e})")
    if data is None:
        bad("Couldn't download portable Python — check the internet connection and run this again")
        return False
    RUNTIME.mkdir(parents=True, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(data)).extractall(RUNTIME)
    enable_site_packages(RUNTIME)

    # Step 4b: pip, then every package in requirements.txt
    try:
        (RUNTIME / "get-pip.py").write_bytes(_download("https://bootstrap.pypa.io/get-pip.py"))
    except Exception as e:
        bad(f"Couldn't download pip ({e})")
        return False
    if subprocess.call([str(exe), str(RUNTIME / "get-pip.py"), "--no-warn-script-location"]):
        bad("pip didn't install into the portable Python")
        return False
    info("Installing Prometheus's packages into it (a few GB, several minutes)…")
    if subprocess.call([str(exe), "-m", "pip", "install", "--no-warn-script-location",
                        "-r", "requirements.txt"]):
        bad("Some packages didn't install — scroll up to see which")
        return False
    probe = subprocess.run([str(exe), "-c", "import PySide6, requests, numpy; print('ok')"],
                           capture_output=True, text=True)
    if "ok" not in probe.stdout:
        bad("The portable Python can't load PySide6:\n" + probe.stderr[-400:])
        return False
    ok(f"Portable Python ready ({_gb(_size(RUNTIME))})")
    return True


# ── Step 5 ──────────────────────────────────────────────────────────────────

LAUNCH_BAT = r"""@echo off
REM Start Prometheus with what's inside this folder (made by tools/make_portable.py).
REM Uses runtime\python if it's there, otherwise the Python on this computer.
cd /d "%~dp0"
set PYTHONUTF8=1
if exist "runtime\python\pythonw.exe" (
    start "" "runtime\python\pythonw.exe" main.py %*
) else (
    python main.py %*
)
"""

LAUNCH_SH = """#!/usr/bin/env bash
# Start Prometheus with what's inside this folder (made by tools/make_portable.py).
cd "$(dirname "$0")"
if [ -d wheels ] && ! python3 -c "import PySide6" 2>/dev/null; then
    echo "First run on this machine: installing packages from ./wheels (offline)"
    python3 -m pip install --no-index --find-links wheels -r requirements.txt
fi
exec python3 main.py "$@"
"""


def step_launchers(check: bool):
    if check:
        return
    (ROOT / "Prometheus.bat").write_text(LAUNCH_BAT.replace("\n", "\r\n"), encoding="ascii", newline="")
    sh = ROOT / "prometheus.sh"
    sh.write_text(LAUNCH_SH, encoding="utf-8", newline="\n")
    sh.chmod(0o755)
    ok("Launchers: Prometheus.bat (Windows), prometheus.sh (Linux/macOS)")


# ── Step 6 ──────────────────────────────────────────────────────────────────

def step_report():
    from core.app.config import Config
    from core.app.paths import setup_dir
    cfg = Config.load()
    print()
    if cfg.obsidian_vault and not _inside(cfg.obsidian_vault):
        warn(f"Your Obsidian vault is outside: {cfg.obsidian_vault} — copy it too, then set it "
             "again in Settings → Obsidian on the new machine")
    if setup_dir().is_dir() and not _inside(setup_dir()):
        info(f"{setup_dir()} (downloads, sources) isn't needed to run — leave it or copy it, either way")
    print(f"\nThe prometheus folder is {_gb(_size(ROOT))}.")


def main() -> int:
    check = "--check" in sys.argv
    print(f"{'Checking' if check else 'Gathering everything into'} {ROOT}\n")
    results = [step_models(check), step_ollama(check), step_voice(check), step_python(check)]
    step_launchers(check)
    step_report()
    if all(results):
        print("\nReady to move: copy the whole prometheus folder and run Prometheus.bat"
              if os.name == "nt" else "\nReady to move: copy the whole prometheus folder and run ./prometheus.sh")
        return 0
    print("\nNot everything is inside yet — see the lines above." +
          ("" if check else " Fix those and run this again."))
    return 1


if __name__ == "__main__":
    sys.exit(main())
