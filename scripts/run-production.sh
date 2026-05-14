#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f ".env.production" ]; then
  echo "Missing .env.production. Copy .env.production.example and fill secrets first." >&2
  exit 1
fi

set -a
source .env.production
set +a

exec .venv/bin/uvicorn app.api:app --host 127.0.0.1 --port "${PORT:-8000}"
