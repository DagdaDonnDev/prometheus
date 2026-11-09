@echo off
REM ============================================================
REM  PROMETHEUS - one-click Windows setup
REM  Double-click this file. It will:
REM    1. Check Python 3.9+
REM    2. Check pip
REM    3. Check Ollama (opens the download page if missing)
REM    4. Pull the default model (LFM2.5 1.2B)
REM    5. Install Python requirements
REM    6. Build the knowledge base index (tools\ingest.py)
REM    7. Offer to launch Prometheus
REM  Knowledge base downloads (tools\bootstrap.py) are a separate step.
REM ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Prometheus setup

echo.
echo  PROMETHEUS SETUP
echo  ----------------
echo.

REM -- Step 1: Python -------------------------------------------
REM Prefer "python" - the same one you'd type to run Prometheus later.
REM ("py" can open a different install, so packages would land elsewhere.)
set "PY="
REM The portable Python inside this folder comes first (tools\make_portable.py)
if exist "runtime\python\Lib\site-packages\pip\" set "PY=runtime\python\python.exe"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY ( where py >nul 2>nul && set "PY=py -3" )
if not defined PY (
    echo [X] Python was not found.
    echo     Install Python 3.9 or newer from https://www.python.org/downloads/
    echo     Tick "Add python.exe to PATH" during install, then run this again.
    start "" https://www.python.org/downloads/
    pause
    exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
    echo [X] Python 3.9 or newer is needed. You have:
    %PY% --version
    start "" https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "delims=" %%v in ('%PY% --version') do echo [OK] %%v

REM -- Step 2: pip ----------------------------------------------
%PY% -m pip --version >nul 2>nul
if errorlevel 1 (
    echo [..] pip missing - installing it
    %PY% -m ensurepip --upgrade
    if errorlevel 1 (
        echo [X] Could not install pip.
        pause
        exit /b 1
    )
)
echo [OK] pip

REM -- Step 3: Ollama -------------------------------------------
where ollama >nul 2>nul
if errorlevel 1 (
    echo [X] Ollama was not found.
    echo     The download page is opening. Install Ollama, then run this again.
    start "" https://ollama.com/download
    pause
    exit /b 1
)
echo [OK] Ollama installed

REM -- Step 4: models ---------------------------------------------
REM Two models, kept in prometheus\models (not your user folder):
REM   speaker   qwen3:1.7b  - talks to you            (about 1.4 GB)
REM   librarian LFM2.5 1.2B - reads the library only  (about 730 MB)
REM Step 4a: already downloaded into Ollama's usual folder? Move them here.
REM Step 4b: otherwise download them straight into prometheus\models.
%PY% -m core.ai.ollama_local --move
for %%M in (qwen3:1.7b hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:latest) do (
    %PY% -m core.ai.ollama_local --has %%M
    if errorlevel 1 (
        echo [..] Downloading %%M into prometheus\models - first time only
        %PY% -m core.ai.ollama_local --pull %%M
        if errorlevel 1 (
            echo [X] Model download failed. Check your internet connection and run this again.
            pause
            exit /b 1
        )
    )
)
echo [OK] Models ready in prometheus\models

REM -- Step 5: requirements -------------------------------------
echo [..] Installing Python packages
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo [X] Package install failed. Scroll up to see which package.
    pause
    exit /b 1
)
echo [OK] Packages installed

REM -- Step 5b: voice (Piper speaks, Whisper listens) -------------
echo [..] Setting up voice
%PY% tools\setup_voice.py
if errorlevel 1 (
    echo [!] Voice isn't fully set up - Prometheus still works by text.
    echo     Fix what's listed above, then run: %PY% tools\setup_voice.py
)

REM -- Step 6: knowledge base -----------------------------------
echo [..] Building the knowledge base index (10-30 min first time)
%PY% tools\ingest.py --init
%PY% tools\ingest.py
if errorlevel 1 (
    echo [!] Indexing reported a problem. Prometheus will still run,
    echo     but searches may be limited. You can re-run: %PY% tools\ingest.py
)
echo [OK] Knowledge base indexed
echo.
echo  To download the full source library later (about 2 GB):
echo      %PY% tools\bootstrap.py
echo      %PY% tools\ingest.py
echo.

REM -- Step 7: launch -------------------------------------------
set /p LAUNCH=Launch Prometheus now? [Y/n]
if /i "!LAUNCH!"=="n" goto :done
start "" %PY% main.py

:done
echo Setup complete.
pause
endlocal
