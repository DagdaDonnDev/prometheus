@echo off
REM ============================================================
REM  PROMETHEUS - one-click Windows setup
REM  Double-click this file. It will:
REM    1. Check Python 3.9+
REM    2. Check pip
REM    3. Check Ollama (opens the download page if missing)
REM    4. Pull the llama3.2:3b model
REM    5. Install Python requirements
REM    6. Build the knowledge base index (ingest.py)
REM    7. Offer to launch Prometheus
REM  Knowledge base downloads (bootstrap.py) are a separate step.
REM ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Prometheus setup

echo.
echo  PROMETHEUS SETUP
echo  ----------------
echo.

REM -- Step 1: Python -------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
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

REM Start the Ollama server if it isn't already answering
ollama list >nul 2>nul
if errorlevel 1 (
    echo [..] Starting Ollama
    start "Ollama" /min ollama serve
    timeout /t 5 /nobreak >nul
)

REM -- Step 4: model --------------------------------------------
echo [..] Pulling llama3.2:3b (about 2 GB, first time only)
ollama pull llama3.2:3b
if errorlevel 1 (
    echo [X] Model download failed. Check your internet connection and run this again.
    pause
    exit /b 1
)
echo [OK] Model ready

REM -- Step 5: requirements -------------------------------------
echo [..] Installing Python packages
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo [X] Package install failed. Scroll up to see which package.
    pause
    exit /b 1
)
echo [OK] Packages installed

REM -- Step 6: knowledge base -----------------------------------
echo [..] Building the knowledge base index (10-30 min first time)
%PY% ingest.py --init
%PY% ingest.py
if errorlevel 1 (
    echo [!] Indexing reported a problem. Prometheus will still run,
    echo     but searches may be limited. You can re-run: %PY% ingest.py
)
echo [OK] Knowledge base indexed
echo.
echo  To download the full source library later (about 2 GB):
echo      %PY% bootstrap.py
echo      %PY% ingest.py
echo.

REM -- Step 7: launch -------------------------------------------
set /p LAUNCH=Launch Prometheus now? [Y/n]
if /i "!LAUNCH!"=="n" goto :done
start "" %PY% main.py

:done
echo Setup complete.
pause
endlocal
