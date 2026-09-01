#!/usr/bin/env bash
# Convenience launcher for the Communication Evaluation Platform backend.
set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "Starting server on http://localhost:5000 ..."
echo "Open that URL in Chrome or Edge to take/demo the assessment."
echo ""
python3 app.py
