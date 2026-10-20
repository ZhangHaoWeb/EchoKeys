@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please create .venv with Python 3.11 or newer first. See README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name EchoKeys --collect-submodules pynput run.py
if errorlevel 1 exit /b 1
echo Built: dist\EchoKeys.exe
pause
