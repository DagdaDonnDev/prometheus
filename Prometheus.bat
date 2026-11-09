@echo off
REM Start Prometheus with what's inside this folder (made by tools\make_portable.py).
REM Uses runtime\python if it's set up (its packages installed), otherwise the
REM Python on this computer.
cd /d "%~dp0"
set PYTHONUTF8=1
if exist "runtime\python\Lib\site-packages\PySide6\" (
    start "" "runtime\python\pythonw.exe" main.py %*
) else (
    python main.py %*
)
