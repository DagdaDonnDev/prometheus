"""
Make the prometheus folder self-contained — copy it to another computer
(same kind: Windows → Windows) and it runs, with nothing to install.

    python tools/make_portable.py            gather everything into the folder
    python tools/make_portable.py --check    only list what's still outside (changes nothing)

Step 1  AI models      both models (speaker + librarian) → prometheus/models
                       (moved from Ollama's usual folder; nothing re-downloaded)
Step 2  Ollama         the Ollama program → prometheus/ollama
                       (Prometheus uses this copy first; your installed one is untouched).
                       Ollama ships GPU libraries for NVIDIA and AMD cards. All are kept by
                       default, so the folder works on whatever card the next PC has; the
                       sizes are listed. --gpu <maker> keeps only one maker's (Vulkan, which
                       works on any card, and the CPU files always stay).
Step 3  Voice          Piper → prometheus/piper; the Whisper model → prometheus/models/whisper
Step 4  Python         Windows: Python's official portable build → prometheus/runtime/python,
                       with every package Prometheus needs installed into it (needs
                       internet this once). Other systems: the packages are saved to
                       prometheus/wheels so a new machine can install them offline.
Step 5  Launchers      Prometheus.exe / prometheus.sh (next to app/) start it with the copies above
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


LIMIT_GIB = 14      # a 16 GB card holds ~14.5 GB as Windows counts it


def _gib(n: int) -> str:
    """Size as Windows Explorer shows it (1 GB = 1024³ bytes)."""
    return f"{n / 2**30:.1f} GB"


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


def detect_gpu() -> str:
    """'nvidia', 'amd', 'intel' or 'none' — the graphics card Ollama will use here."""
    if shutil.which("nvidia-smi"):
        return "nvidia"
    names = ""
    try:
        if os.name == "nt":
            names = subprocess.run(["powershell", "-NoProfile", "-Command",
                                    "(Get-CimInstance Win32_VideoController).Name"],
                                   capture_output=True, text=True, timeout=20).stdout
        elif shutil.which("lspci"):
            names = subprocess.run(["lspci"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        pass
    low = names.lower()
    for key, vendor in (("nvidia", "nvidia"), ("radeon", "amd"), ("amd", "amd"), ("intel", "intel")):
        if key in low:
            return vendor
    return "none"


# GPU library folders Ollama ships, by maker. Vulkan works on any card and is
# always kept as the fallback; the CPU files are always kept.
_GPU_LIBS = {"nvidia": ("cuda",), "amd": ("rocm", "hip")}


def trim_ollama(gpu: str) -> int:
    """
    Remove the GPU libraries this computer's card can't use (e.g. AMD's on an
    NVIDIA PC). Returns bytes freed. gpu='all' keeps everything.
    """
    if gpu == "all" or not OLLAMA_DIR.is_dir():
        return 0
    drop = [prefix for maker, prefixes in _GPU_LIBS.items() if maker != gpu for prefix in prefixes]
    freed = 0
    for d in sorted(OLLAMA_DIR.rglob("*")):
        if d.is_dir() and d.exists() and any(d.name.lower().startswith(x) for x in drop):
            size = _size(d)
            shutil.rmtree(d, ignore_errors=True)
            freed += size
            info(f"removed {d.relative_to(ROOT)} ({_gb(size)}) — not used with this card")
    return freed


def show_gpu_libs():
    """The size of each graphics-card library Ollama has (where its gigabytes go)."""
    rows = []
    for d in OLLAMA_DIR.rglob("*"):
        if d.is_dir() and any(d.name.lower().startswith(x) for x in ("cuda", "rocm", "hip", "vulkan")):
            rows.append((_size(d), d))
    for size, d in sorted(rows, reverse=True):
        kind = ("NVIDIA" if d.name.lower().startswith("cuda") else
                "AMD" if d.name.lower().startswith(("rocm", "hip")) else "any card")
        print(f"     {_gb(size):>8}  {d.relative_to(ROOT)}  ({kind})")
    if rows:
        print(f"     This PC's card: {detect_gpu()}. To keep only one kind:  "
              "python tools/make_portable.py --gpu nvidia   (or amd / intel)")


def step_ollama(check: bool, gpu: str = "all") -> bool:
    from core.ai import ollama_local as ol
    gpu = detect_gpu() if gpu == "auto" else gpu
    exe = ol.find_ollama()
    if exe and _inside(exe):
        freed = 0 if check else trim_ollama(gpu)
        ok(f"Ollama is in the folder ({_gb(_size(OLLAMA_DIR))})"
           + (f" — {_gb(freed)} freed" if freed else ""))
        show_gpu_libs()
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
    trim_ollama(gpu)
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
    show_gpu_libs()
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

    if exe.exists() and _has_packages():
        ok(f"Portable Python is in the folder with its packages ({_gb(_size(RUNTIME))})")
        return True
    if check:
        warn("Portable Python is only half set up (no packages yet)" if exe.exists()
             else "Python and its packages are outside the folder")
        return False
    if exe.exists():
        info("Portable Python is there but its packages aren't — finishing the setup")
        return _install_packages(exe)

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

    return _install_packages(exe)


def _has_packages() -> bool:
    """The portable Python has what Prometheus needs to start."""
    return (RUNTIME / "Lib" / "site-packages" / "PySide6").is_dir()


def _install_packages(exe: Path) -> bool:
    """Step 4b: pip, then every package in requirements.txt (safe to run again)."""
    enable_site_packages(RUNTIME)
    has_pip = (RUNTIME / "Lib" / "site-packages" / "pip").is_dir()
    try:
        if not has_pip:
            (RUNTIME / "get-pip.py").write_bytes(_download("https://bootstrap.pypa.io/get-pip.py"))
    except Exception as e:
        bad(f"Couldn't download pip ({e})")
        return False
    if not has_pip and subprocess.call([str(exe), str(RUNTIME / "get-pip.py"), "--no-warn-script-location"]):
        bad("pip didn't install into the portable Python — run this again; if it keeps "
            "failing, send the lines above")
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

LAUNCH_SH = """#!/usr/bin/env bash
# Start Prometheus (Linux, macOS, Raspberry Pi). Everything it needs is in app/.
# On Windows, double-click Prometheus.exe instead.
cd "$(dirname "$0")/app"
if [ -d wheels ] && ! python3 -c "import PySide6" 2>/dev/null; then
    echo "First run on this machine: installing packages from app/wheels (offline)"
    python3 -m pip install --no-index --find-links wheels -r requirements.txt
fi
exec python3 main.py "$@"
"""


def step_launchers(check: bool):
    """
    Next to the app folder: Prometheus.exe (committed — tools/build_exe.py
    makes it) for Windows, prometheus.sh for Linux/macOS.
    """
    top = ROOT.parent
    exe = top / "Prometheus.exe"
    if check:
        (ok if exe.exists() else bad)(f"Prometheus.exe {'is' if exe.exists() else 'is missing'} next to the app folder")
        return
    sh = top / "prometheus.sh"
    sh.write_text(LAUNCH_SH, encoding="utf-8", newline="\n")
    sh.chmod(0o755)
    if exe.exists():
        ok("Launchers: Prometheus.exe (Windows), prometheus.sh (Linux/macOS)")
    else:
        bad("Prometheus.exe is missing next to the app folder — python tools/build_exe.py makes it")


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
    # Step 6b: does it fit a 16 GB SD card / USB stick? Those hold about
    # 14.5 GB as Windows counts it, so 14 GB is the line.
    total = _size(ROOT)
    print(f"\nThe prometheus folder is {_gib(total)}.")
    if total > LIMIT_GIB * 2**30:
        warn(f"That's over {LIMIT_GIB} GB — it won't fit a 16 GB SD card or USB stick. Biggest parts:")
        parts = sorted(((_size(d), d.name) for d in ROOT.iterdir() if d.is_dir()), reverse=True)[:5]
        for size, name in parts:
            print(f"     {_gib(size):>8}  {name}")
        print("     Ways to shrink it: --gpu nvidia (or amd) keeps one graphics card's libraries;\n"
              "     fewer voices in voices\\; delete knowledge_base\\wikipedia_full.sqlite if present.")
    else:
        ok(f"Fits a 16 GB SD card or USB stick ({_gib(LIMIT_GIB * 2**30 - total)} to spare under {LIMIT_GIB} GB)")


def main() -> int:
    check = "--check" in sys.argv
    gpu = "all"                          # portable: every graphics card keeps working
    if "--gpu" in sys.argv:              # --gpu nvidia|amd|intel|none|auto|all
        i = sys.argv.index("--gpu")
        gpu = sys.argv[i + 1].lower() if i + 1 < len(sys.argv) else "all"
    print(f"{'Checking' if check else 'Gathering everything into'} {ROOT}\n")
    results = [step_models(check), step_ollama(check, gpu), step_voice(check), step_python(check)]
    step_launchers(check)
    step_report()
    if all(results):
        print("\nReady to move: copy the whole prometheus folder (Prometheus.exe + app) and "
              "double-click Prometheus.exe" if os.name == "nt" else
              "\nReady to move: copy the whole prometheus folder and run ./prometheus.sh")
        return 0
    print("\nNot everything is inside yet — see the lines above." +
          ("" if check else " Fix those and run this again."))
    return 1


if __name__ == "__main__":
    sys.exit(main())
