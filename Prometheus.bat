@echo off
REM Start Prometheus with what's inside this folder (made by tools/make_portable.py).
REM Uses runtime\python if it's there, otherwise the Python on this computer.
cd /d "%~dp0"
set PYTHONUTF8=1
if exist "runtime\python\pythonw.exe" (
    start "" "runtime\python\pythonw.exe" main.py %*
) else (
    python main.py %*
)
