#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
uv sync --frozen --python 3.12 --no-editable --extra demo --group dev --reinstall-package pmut-haptics
.venv/bin/python scripts/doctor.py
