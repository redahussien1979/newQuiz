#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "Creating a private Python environment (first run only)..."
  python3 -m venv .venv || { echo "Python 3.10+ is required: https://www.python.org/downloads/"; exit 1; }
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
echo "Starting Video Studio - your browser will open..."
.venv/bin/python app.py
