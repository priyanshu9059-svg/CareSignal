#!/bin/sh
set -eu
cd /app/backend
python migrate.py
python -m app.seed
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}"
