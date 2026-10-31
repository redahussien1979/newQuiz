@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
if not exist ".venv\Scripts\python.exe" (
  echo Creating a private Python environment - first run only...
  %PY% -m venv .venv || (echo Python 3.10 or newer is required: https://www.python.org/downloads/ & pause & exit /b 1)
)
echo Checking packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo Starting Video Studio - your browser will open...
".venv\Scripts\python.exe" app.py
pause
