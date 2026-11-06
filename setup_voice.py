"""
Voice setup — speech in (Faster-Whisper) and speech out (Piper), checked end to end.

    python setup_voice.py            set up everything that's missing, then test it
    python setup_voice.py --check    only report what's there (no downloads)

Step 1: install faster-whisper and sounddevice into THIS Python
Step 2: download the Whisper model into models/whisper/<size> (once; offline after)
Step 3: find Piper, or download the release program into prometheus/piper/
Step 4: find voices in voices/ (one folder per character); offer the ones
        in prometheus_setup/ if voices/ is empty
Step 5: test: Piper says a sentence, Whisper writes down what it heard
Step 6: list the microphones

Needs internet for steps 1–3 the first time only.
"""

import io
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

WHISPER_DIR = ROOT / "models" / "whisper"
PIPER_DIR = ROOT / "piper"
PIPER_RELEASE = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/"
TEST_SENTENCE = "Prometheus can hear you and talk back."


def ok(msg):   print(f"[OK] {msg}")
def info(msg): print(f"[..] {msg}")
def warn(msg): print(f"[!]  {msg}")
def bad(msg):  print(f"[X]  {msg}")


def whisper_size() -> str:
    try:
        from core.config import Config
        return Config.load().stt_model or "tiny"
    except Exception:
        return "tiny"


# ── Step 1 ──────────────────────────────────────────────────────────────────

def _loads(module: str):
    """'' if the module imports, else the reason."""
    import importlib
    importlib.invalidate_caches()
    try:
        importlib.import_module(module)
        return ""
    except Exception as e:
        return str(e) or type(e).__name__


def step_packages(check_only: bool):
    """Returns (whisper works, microphone library works) — checked separately."""
    wanted = {"faster_whisper": "faster-whisper", "sounddevice": "sounddevice"}
    missing = [pkg for mod, pkg in wanted.items() if _loads(mod)]
    if missing and not check_only:
        info(f"Installing {', '.join(missing)} into {sys.executable}")
        if subprocess.call([sys.executable, "-m", "pip", "install", *missing]) != 0:
            v = sys.version_info
            bad("pip couldn't install them.")
            if v >= (3, 14):
                print(f"     This is Python {v.major}.{v.minor}; faster-whisper's engine (ctranslate2) may not\n"
                      "     have a build for it yet. Python 3.12 or 3.13 works — install it, then run\n"
                      "     this script and Prometheus with that Python.")
    whisper_err, mic_err = _loads("faster_whisper"), _loads("sounddevice")
    if whisper_err:
        bad(f"faster-whisper: {whisper_err}")
        if os.name == "nt" and "No module" not in whisper_err:
            print("     On Windows this is usually the Microsoft Visual C++ Redistributable:\n"
                  "     https://aka.ms/vs/17/release/vc_redist.x64.exe — install it and run this again.")
    else:
        ok("faster-whisper installed")
    if mic_err:
        bad(f"sounddevice (microphone): {mic_err}")
        if "PortAudio" in mic_err and sys.platform.startswith("linux"):
            print("     Install PortAudio:  sudo apt install libportaudio2   (then run this again)")
    else:
        ok("sounddevice (microphone) installed")
    return not whisper_err, not mic_err


# ── Step 2 ──────────────────────────────────────────────────────────────────

def step_whisper_model(check_only: bool) -> bool:
    size = whisper_size()
    target = WHISPER_DIR / size
    if (target / "model.bin").is_file():
        ok(f"Whisper model '{size}' in {target.relative_to(ROOT)}")
        return True
    if check_only:
        bad(f"Whisper model '{size}' not downloaded yet")
        return False
    try:
        from faster_whisper.utils import download_model
    except Exception:
        bad("faster-whisper isn't working, so the model can't be downloaded")
        return False
    import warnings
    warnings.filterwarnings("ignore", category=UserWarning)
    info(f"Downloading the Whisper '{size}' model (tiny is about 75 MB)")
    os.environ.pop("HF_HUB_OFFLINE", None)
    try:
        download_model(size, output_dir=str(target))
    except Exception as e:
        bad(f"Download failed: {e}")
        return False
    ok(f"Whisper model '{size}' in {target.relative_to(ROOT)}")
    return True


# ── Step 3 ──────────────────────────────────────────────────────────────────

def _piper_asset() -> str:
    system, machine = platform.system(), platform.machine().lower()
    if system == "Windows":
        return "piper_windows_amd64.zip"
    if system == "Darwin":
        return "piper_macos_aarch64.tar.gz" if machine in ("arm64", "aarch64") else "piper_macos_x64.tar.gz"
    if machine in ("aarch64", "arm64"):
        return "piper_linux_aarch64.tar.gz"
    if machine.startswith("armv7"):
        return "piper_linux_armv7l.tar.gz"
    return "piper_linux_x86_64.tar.gz"


def find_piper():
    from core.voice_manager import VoiceManager
    vm = VoiceManager()
    vm._piper_cache = None
    return vm.find_piper()


def step_piper(check_only: bool):
    found = find_piper()
    if found:
        ok(f"Piper: {found}")
        return found
    if check_only:
        bad("Piper not found")
        return None
    asset = _piper_asset()
    info(f"Downloading Piper ({asset}, about 20 MB)")
    try:
        with urllib.request.urlopen(PIPER_RELEASE + asset, timeout=60) as r:
            data = r.read()
    except Exception as e:
        bad(f"Download failed: {e}")
        print(f"     Get it by hand: {PIPER_RELEASE}{asset}  → unzip into {PIPER_DIR}")
        return None
    # Step 3b: unpack into prometheus/piper (the archive has its own piper/ folder)
    tmp = Path(tempfile.mkdtemp())
    try:
        if asset.endswith(".zip"):
            zipfile.ZipFile(io.BytesIO(data)).extractall(tmp)
        else:
            with tarfile.open(fileobj=io.BytesIO(data)) as t:
                t.extractall(tmp, filter="data") if hasattr(tarfile, "data_filter") else t.extractall(tmp)
        inner = tmp / "piper" if (tmp / "piper").is_dir() else tmp
        if PIPER_DIR.exists():
            shutil.rmtree(PIPER_DIR)
        shutil.copytree(inner, PIPER_DIR)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    exe = PIPER_DIR / ("piper.exe" if os.name == "nt" else "piper")
    if exe.exists() and os.name != "nt":
        exe.chmod(0o755)
    found = find_piper()
    if not found:
        bad(f"Unpacked, but no Piper program in {PIPER_DIR}")
        return None
    ok(f"Piper: {found}")
    return found


# ── Step 4 ──────────────────────────────────────────────────────────────────

def step_voices(check_only: bool):
    from core.voice_manager import VoiceManager, VOICES_DIR
    from core.paths import setup_dir
    vm = VoiceManager()
    if vm.count():
        for v in vm.all_voices():
            note = "" if v.config.exists() else "  (no .onnx.json next to it — Piper needs one)"
            print(f"     {v.name}: {v.model.name}{note}")
        ok(f"{vm.count()} voice(s) in {VOICES_DIR}/")
        return vm.first()
    # Step 4b: voices downloaded into prometheus_setup — copy one per folder
    spare = [p for p in setup_dir().rglob("*.onnx")] if setup_dir().is_dir() else []
    spare = [p for p in spare if Path(str(p) + ".json").exists()]
    if not spare:
        bad("No voices. Put each character in its own folder, e.g. voices/Alan/ with\n"
            "     en_GB-alan-medium.onnx and en_GB-alan-medium.onnx.json\n"
            "     (from huggingface.co/rhasspy/piper-voices)")
        return None
    if check_only:
        warn(f"voices/ is empty, but {len(spare)} voice(s) are in {setup_dir()}")
        return None
    for model in spare[:3]:
        name = model.stem.split("-")[1].title() if "-" in model.stem else model.stem
        folder = VOICES_DIR / name
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model, folder / model.name)
        shutil.copy2(str(model) + ".json", folder / (model.name + ".json"))
        info(f"Copied {model.name} → voices/{name}/")
    vm.scan()
    ok(f"{vm.count()} voice(s) in {VOICES_DIR}/")
    return vm.first()


# ── Step 5 ──────────────────────────────────────────────────────────────────

def step_round_trip(voice, whisper_ready: bool) -> bool:
    from core.voice_manager import VoiceManager
    if voice is None:
        warn("Skipping the speech test (no voice)")
        return False
    out = Path(tempfile.gettempdir()) / "prometheus_voice_test.wav"
    vm = VoiceManager()
    if not vm.speak(TEST_SENTENCE, voice, str(out)) or not out.exists() or out.stat().st_size < 1000:
        bad(f"Piper couldn't speak with {voice.name}. Try it by hand:\n"
            f'     echo hello | "{vm.find_piper()}" --model "{voice.model}" --output_file test.wav')
        return False
    ok(f"Piper spoke with {voice.name} ({out.stat().st_size // 1000} KB of audio)")
    if not whisper_ready:
        warn("Skipping the listening test (Whisper isn't ready)")
        return False
    from core.stt import STTEngine
    from core.config import Config
    stt = STTEngine(Config.load())
    stt.initialize()
    if not stt.available:
        bad(f"Whisper didn't load: {stt.error}")
        return False
    heard = stt.transcribe_file(str(out))
    print(f'     said:  "{TEST_SENTENCE}"\n     heard: "{heard}"')
    words = lambda s: {w.strip(".,!?").lower() for w in s.split()}
    if len(words(TEST_SENTENCE) & words(heard)) >= 4:
        ok("Whisper understood Piper")
        return True
    warn("Whisper heard something different — voice works, but check the result above")
    return False


# ── Step 6 ──────────────────────────────────────────────────────────────────

def step_microphones():
    try:
        import sounddevice as sd
        devices = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
    except Exception as e:
        warn(f"Couldn't list microphones: {e}")
        return
    if not devices:
        warn("No microphone found")
        return
    default = sd.default.device[0] if sd.default.device else None
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) > 0:
            mark = "  ← default" if i == default else ""
            print(f"     {d['name']}{mark}")
    ok(f"{len(devices)} microphone(s)")


def main() -> int:
    check_only = "--check" in sys.argv
    print(f"Voice setup — Python {platform.python_version()} ({sys.executable})\n")
    whisper, mic = step_packages(check_only)
    model = step_whisper_model(check_only) if whisper else False
    piper = step_piper(check_only)
    voice = step_voices(check_only) if piper else None
    print()
    passed = step_round_trip(voice, whisper and model) if piper else False
    if mic:
        step_microphones()
    print()
    if whisper and mic and model and piper and voice is not None and passed:
        ok("Voice is ready. Restart Prometheus; the mic button and spoken replies will work.")
        return 0
    warn("Voice isn't fully ready — see the [X] lines above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
