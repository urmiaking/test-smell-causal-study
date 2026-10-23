#!/usr/bin/env bash
set -euo pipefail
PYTHON_BIN=${PYTHON_BIN:-python3}
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m team7_pipeline doctor
