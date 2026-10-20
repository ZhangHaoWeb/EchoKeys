@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please follow README.md to create .venv and install dependencies first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m echokeys
if errorlevel 1 pause
