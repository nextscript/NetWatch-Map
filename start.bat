@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0"
title Network Map - Live Connection Monitor
color 0B

echo.
echo  ===========================================
echo         NETWORK MAP - Live Monitor
echo  ===========================================
echo.

set "PYTHON_EXE="

if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "venv\Scripts\python.exe" set "PYTHON_EXE=venv\Scripts\python.exe"

if not defined PYTHON_EXE (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=py -3"
)

if not defined PYTHON_EXE (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE goto :python_missing

for /f "delims=" %%v in ('%PYTHON_EXE% -c "import sys; print(f""{sys.version_info.major}.{sys.version_info.minor}"")" 2^>nul') do set "PYTHON_VERSION=%%v"
if not defined PYTHON_VERSION goto :python_missing

for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set /a PY_MAJOR=%%a
    set /a PY_MINOR=%%b
)

if %PY_MAJOR% LSS 3 goto :python_version_error
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 9 goto :python_version_error

echo  [1/2] Installing dependencies...
%PYTHON_EXE% -m pip install -r requirements.txt
if errorlevel 1 goto :pip_failed

echo.
echo  [2/2] Starting server...
echo  Open http://localhost:5000 in your browser
echo.
%PYTHON_EXE% app.py
goto :end

:python_missing
echo  No usable Python installation found.
echo.
echo  On Windows 11, the Microsoft Store alias is often enabled instead of a real Python install.
echo  That can cause errors such as "Access denied" or an empty Python lookup.
echo.
echo  Fix it like this:
echo  1. Install Python 3.9 or newer from https://www.python.org/downloads/windows/
echo  2. Enable "Add python.exe to PATH" during setup
echo  3. Optional: Windows Settings ^> Apps ^> Advanced app settings ^> App execution aliases
echo     Disable the aliases for python.exe and python3.exe if they point to the Store
echo.
pause
exit /b 1

:python_version_error
echo  The detected Python version %PYTHON_VERSION% is too old.
echo  This project requires Python 3.9 or newer.
echo.
pause
exit /b 1

:pip_failed
echo.
echo  Dependency installation failed.
echo  Check your internet access, permissions, and Python installation.
echo.
pause
exit /b 1

:end
echo.
pause
