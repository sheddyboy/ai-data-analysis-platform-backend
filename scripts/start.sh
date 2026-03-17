#!/usr/bin/env bash
set -euo pipefail

echo "=== AI Data Analysis Platform — startup ==="

# Render free plan injects $PORT at runtime. Fall back to 8000 for local use.
PORT="${PORT:-8000}"

# /tmp is the only writable path on Render's Python runtime (no persistent disk).
mkdir -p /tmp/uploads
mkdir -p /tmp/data

echo ">>> Running Alembic migrations..."
alembic upgrade head
echo ">>> Migrations complete."

echo ">>> Starting uvicorn on port ${PORT}..."
# exec replaces this shell so OS signals (SIGTERM) go directly to uvicorn.
# --workers 1 keeps memory within Render free plan's 512 MB limit.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers 1 \
  --log-level info
