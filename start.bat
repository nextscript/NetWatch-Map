@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

cd /d "%~dp0"
title Network Map - Live Verbindungsmonitor
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

echo  [1/2] Installiere Abhaengigkeiten...
%PYTHON_EXE% -m pip install -r requirements.txt
if errorlevel 1 goto :pip_failed

echo.
echo  [2/2] Starte Server...
echo  Oeffne http://localhost:5000 im Browser
echo.
%PYTHON_EXE% app.py
goto :end

:python_missing
echo  Kein nutzbares Python gefunden.
echo.
echo  Unter Windows 11 ist oft nur der Microsoft-Store-Alias aktiv.
echo  Das fuehrt zu Fehlern wie "Zugriff verweigert" oder einer leeren Python-Suche.
echo.
echo  So behebst du das:
echo  1. Python 3.9 oder neuer von https://www.python.org/downloads/windows/ installieren
echo  2. Beim Setup "Add python.exe to PATH" aktivieren
echo  3. Optional: Windows-Einstellungen ^> Apps ^> Erweiterte App-Einstellungen ^> App-Ausfuehrungsaliase
echo     Dort die Aliase fuer python.exe und python3.exe deaktivieren, wenn sie auf den Store zeigen
echo.
pause
exit /b 1

:python_version_error
echo  Gefundenes Python %PYTHON_VERSION% ist zu alt.
echo  Dieses Projekt braucht Python 3.9 oder neuer.
echo.
pause
exit /b 1

:pip_failed
echo.
echo  Installation der Abhaengigkeiten ist fehlgeschlagen.
echo  Pruefe Internetzugang, Rechte und deine Python-Installation.
echo.
pause
exit /b 1

:end
echo.
pause
