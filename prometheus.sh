#!/usr/bin/env bash
# Start Prometheus with what's inside this folder (made by tools/make_portable.py).
cd "$(dirname "$0")"
if [ -d wheels ] && ! python3 -c "import PySide6" 2>/dev/null; then
    echo "First run on this machine: installing packages from ./wheels (offline)"
    python3 -m pip install --no-index --find-links wheels -r requirements.txt
fi
exec python3 main.py "$@"
