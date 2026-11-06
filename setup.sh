#!/usr/bin/env bash
# ============================================================
#  PROMETHEUS — one-command setup for Linux, macOS and Raspberry Pi
#    bash setup.sh
#  Same steps as setup.bat:
#    1. Check Python 3.9+      2. Check pip
#    3. Check / install Ollama 4. Pull LFM2.5 1.2B
#    5. Install requirements   6. Build the knowledge base index
#    7. Offer to launch
#  Knowledge base downloads (bootstrap.py) are a separate step.
# ============================================================
set -u
cd "$(dirname "$0")"

ok()   { echo "[OK] $*"; }
info() { echo "[..] $*"; }
fail() { echo "[X] $*"; exit 1; }

echo
echo " PROMETHEUS SETUP"
echo " ----------------"
echo

# Step 1: Python
PY=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || fail "Python was not found. Install Python 3.9 or newer, then run this again."
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
    || fail "Python 3.9 or newer is needed. You have $("$PY" --version 2>&1)."
ok "$("$PY" --version 2>&1)"

# Step 2: pip
if ! "$PY" -m pip --version >/dev/null 2>&1; then
    info "pip missing — installing it"
    "$PY" -m ensurepip --upgrade || fail "Could not install pip (try: sudo apt install python3-pip)."
fi
ok "pip"

# Debian 12+ / Raspberry Pi OS refuse system-wide pip installs
PIP_EXTRA=""
if "$PY" -m pip install --help 2>/dev/null | grep -q -- "--break-system-packages" \
   && [ -z "${VIRTUAL_ENV:-}" ] \
   && ls /usr/lib/python3*/EXTERNALLY-MANAGED >/dev/null 2>&1; then
    PIP_EXTRA="--break-system-packages"
fi

# Step 3: Ollama
if ! command -v ollama >/dev/null 2>&1; then
    info "Ollama not found — installing it"
    curl -fsSL https://ollama.com/install.sh | sh || fail "Ollama install failed. See https://ollama.com/download"
fi
ok "Ollama installed"

# Step 4: model — kept in prometheus/models, not your home folder.
#   4a: already downloaded into Ollama's usual folder? Move it here.
#   4b: otherwise download it straight into prometheus/models.
MODEL="hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest"
"$PY" -m core.ollama_local --move || true
if ! "$PY" -m core.ollama_local --has "$MODEL"; then
    info "Downloading LFM2.5 1.2B Instruct into prometheus/models (about 730 MB, first time only)"
    "$PY" -m core.ollama_local --pull "$MODEL" || fail "Model download failed. Check your connection and run this again."
fi
ok "Model ready in prometheus/models"

# Step 5: requirements
info "Installing Python packages"
"$PY" -m pip install $PIP_EXTRA -r requirements.txt || fail "Package install failed. Scroll up to see which package."
ok "Packages installed"

# Step 5b: voice (Piper speaks, Whisper listens) — optional
info "Setting up voice"
"$PY" setup_voice.py || echo "[!] Voice isn't fully set up — Prometheus still works by text. Fix what's listed above, then run: $PY setup_voice.py"

# Step 6: knowledge base
info "Building the knowledge base index (10–30 min first time)"
"$PY" ingest.py --init
"$PY" ingest.py || echo "[!] Indexing reported a problem. You can re-run: $PY ingest.py"
ok "Knowledge base indexed"
echo
echo " To download the full source library later (about 2 GB):"
echo "     $PY bootstrap.py"
echo "     $PY ingest.py"
echo

# Step 7: launch
read -r -p "Launch Prometheus now? [Y/n] " LAUNCH
case "${LAUNCH:-y}" in
    n|N) ;;
    *)   exec "$PY" main.py ;;
esac
echo "Setup complete."
