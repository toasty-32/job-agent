@echo off
rem Double-click to set up the job agent on Windows.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-windows.ps1"
pause
