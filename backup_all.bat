@echo off
REM backup_all.bat
REM Double-click to run a full backup. Wraps backup_all.ps1 with execution policy bypass.
REM
REM Optional first arg: target host (defaults to pi@192.168.0.217)
REM   backup_all.bat pi@100.76.203.111

setlocal
cd /d "%~dp0"

set TARGET=%1
if "%TARGET%"=="" set TARGET=pi@192.168.0.217

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup_all.ps1" -Target "%TARGET%"

echo.
pause
endlocal
