@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
if not exist ".venv\Scripts\python.exe" (
  echo Creating a private Python environment - first run only...
  %PY% -m venv .venv || (echo Python 3.10 or newer is required: https://www.python.org/downloads/ & pause & exit /b 1)
)
rem Packages are installed only on the first run and when requirements.txt changes (a new version of the app):
rem checking them over the internet on every start took most of the start-up time.
fc /b requirements.txt ".venv\installed-requirements.txt" >nul 2>nul || (
  echo Installing packages - first run or new version only...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt && copy /y requirements.txt ".venv\installed-requirements.txt" >nul
)
set GRADIO_ANALYTICS_ENABLED=False
echo Starting Video Studio - your browser will open...
".venv\Scripts\python.exe" app.py
pause
