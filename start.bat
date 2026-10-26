@echo off
REM ==============================================================================
REM AgentReliability AI — Windows One-Command Setup & Launch
REM ==============================================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ================================================================================
echo  AgentReliability AI - Windows Developer Self-Service Launcher
echo ================================================================================
echo.

REM 1. Check Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found in your PATH.
    echo Please install Python 3.9+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 2. Setup backend\.venv
set "VENV_DIR=%~dp0backend\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

if not exist "%VENV_PY%" (
    echo [1/3] Creating isolated Python virtual environment at backend\.venv...
    python -m venv "%VENV_DIR%"
    "%VENV_PIP%" install --upgrade pip setuptools --quiet
    echo Done.
)

REM 3. Check and install dependencies
"%VENV_PY%" -c "import fastapi, uvicorn, pydantic, sqlite3, agentreliability" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [2/3] Installing backend and SDK dependencies...
    if exist "%~dp0backend\requirements.txt" (
        "%VENV_PIP%" install -r "%~dp0backend\requirements.txt"
    )
    if exist "%~dp0sdk" (
        "%VENV_PIP%" install -e "%~dp0sdk"
    )
    echo Done.
)

REM 4. Check frontend dependencies
where npm >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    if not exist "%~dp0frontend\node_modules" (
        echo [3/3] Installing frontend dependencies with npm...
        npm --prefix "%~dp0frontend" install
        echo Done.
    )
) else (
    echo [WARNING] npm was not found. Dashboard UI may not start.
)

REM 5. Initialize and Launch
echo.
echo Initializing local database and port resolution...
"%VENV_PY%" -m agentreliability.cli init

echo.
echo Starting AgentReliability services...
"%VENV_PY%" -m agentreliability.cli dev %*

