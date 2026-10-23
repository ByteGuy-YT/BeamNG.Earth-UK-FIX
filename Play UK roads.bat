@echo off
setlocal
cd /d "%~dp0"
rem Uses this source folder and its prepared UK index. No change to global Python or other mods.
if not exist ".venv\Scripts\python.exe" (
  echo The local server setup is missing. Run the installer first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import numpy, PIL, duckdb, fsspec, certifi" 2>nul
if errorlevel 1 (
  echo The local server packages are incomplete. Run the installer first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" launcher.py -- %*
echo.
echo Stopped.
pause
