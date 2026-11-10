"""
Prometheus's own Ollama — the model lives in prometheus/models, not in the
user's home folder, so the whole app is one folder you can copy or back up.

How it works:
  - Ollama keeps models wherever OLLAMA_MODELS points. Prometheus starts its
    own `ollama serve` with OLLAMA_MODELS=<prometheus>/models on port 11435,
    so it never clashes with an Ollama app that's already running on 11434.
  - It's only used once prometheus/models has a model in it. Until then the
    app talks to the normal Ollama as before.
  - Moving: `python -m core.ai.ollama_local --move` copies the model from
    Ollama's usual folder into prometheus/models (checking every file), then
    removes it from the old folder. No download needed.
  - New models: `python -m core.ai.ollama_local --pull NAME` downloads straight
    into prometheus/models.

Standard library only — setup.bat runs this before the packages are installed.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Set

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = PROJECT_DIR / "models"
HOST = "127.0.0.1:11435"
URL = f"http://{HOST}"
# If 11435 is taken by an Ollama that isn't serving THIS folder's models (one
# left running from before the folder moved, say), the next port is used
PORTS = (11435, 11436, 11437, 11438)
SERVE_LOG = PROJECT_DIR / "logs" / "ollama_serve.log"
DEFAULT_MODEL = "hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest"   # the librarian
SPEAKER_MODEL = "qwen3:1.7b"                                        # the speaker

_proc: Optional[subprocess.Popen] = None


# ── Where things are ────────────────────────────────────────────────────────

def default_store() -> Path:
    """Ollama's usual model folder (or wherever the user's OLLAMA_MODELS says)."""
    env = os.environ.get("OLLAMA_MODELS")
    if env and Path(env).resolve() != MODELS_DIR.resolve():
        return Path(env)
    return Path.home() / ".ollama" / "models"


def find_ollama() -> Optional[str]:
    """
    The ollama program: the copy inside the prometheus folder first
    (tools/make_portable.py puts it there), then PATH, then where the
    Windows/macOS installers put it.
    """
    for own in (PROJECT_DIR / "ollama" / "ollama.exe", PROJECT_DIR / "ollama" / "bin" / "ollama"):
        if own.is_file() and (os.name == "nt" or os.access(own, os.X_OK)):
            return str(own)
    found = shutil.which("ollama")
    if found:
        return found
    candidates = []
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        candidates += [Path(local) / "Programs" / "Ollama" / "ollama.exe",
                       Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Ollama" / "ollama.exe"]
    else:
        candidates += [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama"),
                       Path("/Applications/Ollama.app/Contents/Resources/ollama")]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def _manifest_files(store: Path) -> List[Path]:
    root = store / "manifests"
    return [p for p in root.rglob("*") if p.is_file()] if root.is_dir() else []


def local_models() -> List[str]:
    """Model names in prometheus/models, as Ollama shows them."""
    out = []
    for p in _manifest_files(MODELS_DIR):
        parts = list(p.relative_to(MODELS_DIR / "manifests").parts)
        tag = parts.pop()
        if parts[0] == "registry.ollama.ai":
            parts = parts[2:] if parts[1] == "library" else parts[1:]
        out.append("/".join(parts) + ":" + tag)
    return sorted(out)


def has_local_models() -> bool:
    return bool(_manifest_files(MODELS_DIR))


def _manifest_rel(name: str) -> Path:
    """
    'hf.co/LiquidAI/X:latest' → manifests/hf.co/LiquidAI/X/latest
    'llama3.2:3b'             → manifests/registry.ollama.ai/library/llama3.2/3b
    """
    name, _, tag = name.partition(":")
    parts = name.split("/")
    # A host only when there's more after it ("hf.co/…"); "llama3.2" is a name
    if len(parts) == 1 or "." not in parts[0]:
        parts = ["registry.ollama.ai"] + (["library"] if len(parts) == 1 else []) + parts
    return Path("manifests", *parts, tag or "latest")


def _find_manifest(store: Path, name: str) -> Optional[Path]:
    """The model's manifest in a store (case doesn't matter — Ollama may lower-case)."""
    want = str(_manifest_rel(name)).replace("\\", "/").lower()
    for p in _manifest_files(store):
        if str(p.relative_to(store)).replace("\\", "/").lower() == want:
            return p
    return None


def _blob_path(store: Path, digest: str) -> Optional[Path]:
    """Ollama names blobs sha256-<hex> (older Linux/macOS builds: sha256:<hex>)."""
    for name in (digest.replace(":", "-"), digest):
        p = store / "blobs" / name
        if p.is_file():
            return p
    return None


def _digests(manifest: Path) -> List[str]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    out = [data["config"]["digest"]] if data.get("config", {}).get("digest") else []
    out += [layer["digest"] for layer in data.get("layers", []) if layer.get("digest")]
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


# ── Moving a model into prometheus/models ───────────────────────────────────

def move_model(name: str, src: Optional[Path] = None, dst: Path = MODELS_DIR,
               remove_old: bool = True, say=print) -> bool:
    """
    Step 1: find the model's manifest in Ollama's usual folder
    Step 2: copy every file it lists into prometheus/models, checking each
            one's SHA-256 (an interrupted copy is never left looking complete)
    Step 3: copy the manifest last — only then does the model exist here
    Step 4: remove it from the old folder: its manifest, and the blobs no
            other model there still uses (what `ollama rm` does)
    """
    src = src or default_store()
    # Step 1
    manifest = _find_manifest(src, name)
    if manifest is None:
        if _find_manifest(dst, name):
            say(f"[OK] {name} is already in {dst}")
            return True
        say(f"[..] {name} isn't in {src}")
        return False
    if _find_manifest(dst, name):
        # Moved before, but the old copy couldn't be removed then
        say(f"[OK] {name} is already in {dst}")
        return _finish_removal(src, manifest, say) if remove_old else True
    # Step 2
    digests = _digests(manifest)
    (dst / "blobs").mkdir(parents=True, exist_ok=True)
    for d in digests:
        blob = _blob_path(src, d)
        if blob is None:
            say(f"[X] {name}: a file is missing from {src / 'blobs'} ({d[:19]}…) — not moved")
            return False
        target = dst / "blobs" / d.replace(":", "-")
        if target.is_file() and target.stat().st_size == blob.stat().st_size and _sha256(target) == d:
            continue
        size_mb = blob.stat().st_size / 1e6
        if size_mb > 50:
            say(f"[..] copying {size_mb:,.0f} MB")
        part = target.with_suffix(".partial")
        shutil.copyfile(blob, part)
        if _sha256(part) != d:
            part.unlink(missing_ok=True)
            say(f"[X] {name}: a copied file didn't match — not moved")
            return False
        os.replace(part, target)
    # Step 3
    rel = manifest.relative_to(src)
    (dst / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(manifest, dst / rel)
    say(f"[OK] {name} is now in {dst}")
    # Step 4
    return _finish_removal(src, manifest, say) if remove_old else True


def _finish_removal(src: Path, manifest: Path, say) -> bool:
    freed, ok = _remove_from(src, manifest)
    if freed:
        say(f"[OK] removed from {src} ({freed / 1e6:,.0f} MB freed)")
    if not ok:
        say("[!] The old copy is still in use. Quit Ollama (its tray icon → Quit) and run this "
            "again to free that space. Prometheus already uses the new copy.")
    return True


def _remove_from(store: Path, manifest: Path):
    """
    Delete the blobs only this model uses, then its manifest. If a blob
    can't be deleted (Ollama has it open), the manifest stays so running
    again finishes the job. Returns (bytes freed, finished).
    """
    try:
        mine = set(_digests(manifest))
    except (OSError, ValueError, KeyError):
        return 0, False
    still_used: Set[str] = set()
    for other in _manifest_files(store):
        if other == manifest:
            continue
        try:
            still_used.update(_digests(other))
        except (OSError, ValueError, KeyError):
            still_used.update(mine)        # can't read it — keep everything
    freed, finished = 0, True
    for d in mine - still_used:
        blob = _blob_path(store, d)
        if blob:
            try:
                size = blob.stat().st_size
                blob.unlink()
                freed += size
            except OSError:
                finished = False
    if finished:
        try:
            manifest.unlink()
        except OSError:
            finished = False
    return freed, finished


# ── Running it ──────────────────────────────────────────────────────────────

# Local requests never go through a proxy (a system proxy would swallow them)
_direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def answering(url: str = "", timeout: float = 1.5) -> bool:
    url = url or URL
    try:
        with _direct.open(f"{url}/api/tags", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def serves_ours(url: str) -> bool:
    """Is the Ollama at url the one for this folder (it lists our models)?"""
    try:
        with _direct.open(f"{url}/api/tags", timeout=1.5) as r:
            names = {m.get("name", "") for m in json.loads(r.read()).get("models", [])}
    except Exception:
        return False
    return bool(names & set(local_models()))


def _use(port: int):
    global HOST, URL
    HOST = f"127.0.0.1:{port}"
    URL = f"http://{HOST}"


def _listening_pid(port: int) -> Optional[int]:
    """The process listening on 127.0.0.1:port, if it can be told."""
    try:
        if os.name == "nt":
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                                 timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3].upper() == "LISTENING":
                    return int(parts[4])
        elif shutil.which("lsof"):
            out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                                 capture_output=True, text=True, timeout=10).stdout.split()
            return int(out[0]) if out else None
    except Exception:
        pass
    return None


def _process_name(pid: int) -> str:
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, timeout=10,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            return out.split(",")[0].strip('" \r\n').lower() if out.strip().startswith('"') else ""
        return Path(f"/proc/{pid}/comm").read_text().strip().lower()
    except Exception:
        return ""


def clear_stale() -> List[str]:
    """
    An Ollama left on Prometheus's own ports that isn't serving this folder's
    models (one from before the folder moved) is stopped — it can hold memory
    on the graphics card. Only ollama processes, only on PORTS (the usual
    Ollama on 11434 is never touched). Returns what it did, for the log.
    """
    done = []
    for port in PORTS:
        url = f"http://127.0.0.1:{port}"
        if not answering(url, timeout=0.5) or serves_ours(url):
            continue
        pid = _listening_pid(port)
        name = _process_name(pid) if pid else ""
        if not pid or not name.startswith("ollama"):
            continue
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                os.kill(pid, 15)
            done.append(f"stopped an old Ollama on port {port} (pid {pid})")
        except Exception as e:
            done.append(f"couldn't stop the old Ollama on port {port}: {e}")
    return done


def gpu_report() -> List[str]:
    """For the debug log: graphics card memory, and what's using it (NVIDIA)."""
    if not shutil.which("nvidia-smi"):
        return []
    run = lambda *a: subprocess.run(["nvidia-smi", *a], capture_output=True, text=True, timeout=15,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    try:
        lines = []
        for row in run("--query-gpu=name,memory.used,memory.total", "--format=csv,noheader").splitlines():
            lines.append(f"Graphics card:      {row.strip()}")
        apps = [r.strip() for r in run("--query-compute-apps=process_name,used_memory",
                                       "--format=csv,noheader").splitlines() if r.strip()]
        if apps:
            lines.append("Using it:           " + "; ".join(apps[:8]))
        return lines
    except Exception:
        return []


def _pick_port() -> int:
    """
    Step 1: a port where our own Ollama already runs → reuse it
    Step 2: else the first free one. A port answered by an Ollama with other
            models (the old folder's, before the move) is skipped — it
            would say our models don't exist.
    """
    free = None
    for port in PORTS:
        url = f"http://127.0.0.1:{port}"
        if not answering(url, timeout=0.5):
            free = free or port
        elif serves_ours(url):
            return port
    return free or PORTS[-1]


def _env() -> Dict[str, str]:
    env = dict(os.environ)
    env["OLLAMA_MODELS"] = str(MODELS_DIR)
    env["OLLAMA_HOST"] = HOST
    return env


def start(wait: float = 0) -> bool:
    """
    Start Prometheus's own Ollama if there's a model in prometheus/models.
    True if it's answering (or starting). Already running with our models →
    reused; one serving other models is left alone and another port is used.
    """
    global _proc
    if not has_local_models():
        return False
    if _proc is not None and _proc.poll() is None:
        return True
    clear_stale()
    _use(_pick_port())
    if answering():
        return True               # ours, already running
    exe = find_ollama()
    if not exe:
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # What Ollama says goes to logs/ollama_serve.log — if it won't start or
    # can't read the models, the reason is there (shown by --status)
    try:
        SERVE_LOG.parent.mkdir(exist_ok=True)
        out = open(SERVE_LOG, "w", encoding="utf-8", errors="replace")
    except OSError:
        out = subprocess.DEVNULL
    try:
        _proc = subprocess.Popen([exe, "serve"], env=_env(), stdout=out,
                                 stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 creationflags=flags)
    except OSError as e:
        _proc = None
        if out is not subprocess.DEVNULL:
            out.write(f"Couldn't start {exe}: {e}\n")
            out.close()
        return False
    end = time.time() + wait
    while time.time() < end and not answering():
        time.sleep(0.25)
    return True


def active_url() -> str:
    """Our own server's address if it's in use, else ''."""
    if not has_local_models():
        return ""
    if (_proc is not None and _proc.poll() is None) or answering(timeout=0.5):
        return URL
    return ""


def stop():
    """Stop the server we started (never someone else's)."""
    global _proc
    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None


def pull(name: str) -> int:
    """Download a model straight into prometheus/models."""
    exe = find_ollama()
    if not exe:
        print("[X] Ollama isn't installed — https://ollama.com/download")
        return 1
    MODELS_DIR.mkdir(exist_ok=True)
    started = None
    _use(_pick_port())
    if not answering():
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        started = subprocess.Popen([exe, "serve"], env=_env(), stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=flags)
        for _ in range(60):
            if answering():
                break
            time.sleep(0.5)
    try:
        return subprocess.call([exe, "pull", name], env=_env())
    finally:
        if started is not None:
            started.terminate()


def _configured_models() -> List[str]:
    """The models Settings uses (memory/config.json), else the default."""
    try:
        from core.app.config import CONFIG_PATH
        data = json.loads(Path(CONFIG_PATH).read_text(encoding="utf-8"))
        names = {data.get("speaker_model") or SPEAKER_MODEL,
                 data.get("librarian_model") or DEFAULT_MODEL}
        return sorted(n for n in names if n)
    except Exception:
        return [SPEAKER_MODEL, DEFAULT_MODEL]


def status() -> int:
    """For the debug log: everything that decides whether the models load."""
    exe = find_ollama()
    print(f"Ollama program:     {exe or 'NOT FOUND'}")
    print(f"Models folder:      {MODELS_DIR}")
    names = local_models()
    print(f"Models in it:       {', '.join(names) or 'none'}")
    for name in names:
        m = _find_manifest(MODELS_DIR, name)
        missing = [d for d in _digests(m) if not _blob_path(MODELS_DIR, d)] if m else []
        if missing:
            print(f"  [X] {name}: {len(missing)} file(s) missing from models\\blobs")
    wanted = _configured_models()
    gone = [n for n in wanted if n not in names]
    if gone:
        print(f"  [!] Settings use {', '.join(gone)} — not in the models folder")
    for port in PORTS:
        url = f"http://127.0.0.1:{port}"
        if answering(url, timeout=0.5):
            print(f"Port {port}:         an Ollama is running — "
                  + ("ours (has these models)" if serves_ours(url) else "NOT ours (other models; skipped)"))
    for line in gpu_report():
        print(line)
    try:
        tail = SERVE_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
        if tail:
            print("Last lines of logs\\ollama_serve.log (our Ollama's own output, last start):")
            for line in tail:
                print("  " + line[:200])
    except OSError:
        pass
    return 0


def main(argv: List[str]) -> int:
    """
    python -m core.ai.ollama_local --move [NAME…]   move models into prometheus/models
    python -m core.ai.ollama_local --pull NAME      download one there
    python -m core.ai.ollama_local --has NAME       exit code 0 if it's there
    python -m core.ai.ollama_local --list           what's there
    python -m core.ai.ollama_local --status         which Ollama, which models, what's running
    """
    if not argv or argv[0] in ("-h", "--help"):
        print(main.__doc__)
        return 0
    if argv[0] == "--move":
        names = argv[1:] or _configured_models()
        ok = all([move_model(n) for n in names])
        return 0 if ok else 1
    if argv[0] == "--has" and len(argv) > 1:
        return 0 if _find_manifest(MODELS_DIR, argv[1]) else 1
    if argv[0] == "--pull" and len(argv) > 1:
        return pull(argv[1])
    if argv[0] == "--list":
        for name in local_models():
            print(name)
        return 0
    if argv[0] == "--status":
        return status()
    print(main.__doc__)
    return 1


if __name__ == "__main__":
    os.chdir(PROJECT_DIR)
    sys.exit(main(sys.argv[1:]))
