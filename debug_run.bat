@echo off
REM ============================================================
REM  debug_run.bat - TEMPORARY: run Prometheus and save a log
REM
REM  Double-click it. When you close Prometheus, everything is
REM  saved to logs\run_<date>_<time>.log:
REM    1. versions: Python, PySide6, Ollama, installed models
REM    2. everything Prometheus printed (errors included)
REM    3. the last 10 replies and where each one's wait came from
REM  Send that file when something's wrong. Delete this .bat any time.
REM ============================================================
setlocal
cd /d "%~dp0"

REM UTF-8 everywhere, otherwise emoji in the output crash Python on Windows
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
chcp 65001 >nul

REM Use the Python that actually has Prometheus's packages installed.
REM ("py" can open a different install than "python" - e.g. a fresh 3.14
REM from the Python install manager with nothing in it.)
set "PY="
REM The portable Python inside this folder comes first (tools\make_portable.py)
if exist "runtime\python\Lib\site-packages\PySide6\" set "PY=runtime\python\python.exe"
for %%P in ("python" "py -3" "python3") do (
  if not defined PY (
    %%~P -c "import PySide6, requests" >nul 2>nul && set "PY=%%~P"
  )
)
if not defined PY (
  set "PY=python"
  echo No Python here has PySide6 installed yet. Run:  python -m pip install -r requirements.txt
)
echo Using: %PY%

REM Timestamped log file (PowerShell gives the same format on every Windows language)
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "TS=%%i"
if not exist logs mkdir logs
set "LOG=logs\run_%TS%.log"

echo Running Prometheus. Close the window when you're done - the log saves then.
echo Log: %LOG%

REM -- Step 1: versions --------------------------------------------
(
  echo ===== Prometheus debug run %TS% =====
  echo.
  echo --- Python ---
  %PY% --version
  %PY% -c "import PySide6, sys; print('PySide6', PySide6.__version__); print(sys.executable)"
  echo.
  echo --- Ollama ---
  ollama --version
  echo Models in prometheus\models:
  %PY% -m core.ai.ollama_local --list
  echo Models in Ollama's usual folder:
  ollama list
  echo Loaded right now:
  ollama ps
  echo.
  echo --- Settings ^(memory\config.json^) ---
  if exist memory\config.json ( type memory\config.json ) else ( echo none yet )
  echo.
  echo ===== Prometheus output =====
) > "%LOG%" 2>&1

REM -- Step 2: run the app, capturing everything it prints ----------
%PY% main.py >> "%LOG%" 2>&1
set "CODE=%ERRORLEVEL%"

REM -- Step 3: what happened -----------------------------------------
(
  echo.
  echo ===== Prometheus closed, exit code %CODE% =====
  echo.
  echo --- Replies this run ^(last 10^) ---
  %PY% -m core.answers.tracer 10
  echo.
  echo --- Ollama after the run ---
  ollama ps
) >> "%LOG%" 2>&1

echo.
echo Saved: %LOG%
if not "%CODE%"=="0" echo Prometheus exited with an error - the log has the details.
start "" explorer /select,"%CD%\%LOG%"
pause
endlocal
