#!/usr/bin/env bash
# Start Prometheus (Linux, macOS, Raspberry Pi). Everything it needs is in app/.
# On Windows, double-click Prometheus.exe instead.
cd "$(dirname "$0")/app"
if [ -d wheels ] && ! python3 -c "import PySide6" 2>/dev/null; then
    echo "First run on this machine: installing packages from app/wheels (offline)"
    python3 -m pip install --no-index --find-links wheels -r requirements.txt
fi
exec python3 main.py "$@"
