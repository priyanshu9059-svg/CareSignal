#!/bin/sh
set -eu
cd /app/backend
python migrate.py
if [ "${DEMO_ENABLED:-true}" = "true" ]; then
  python -m app.seed
fi
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}"
