#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/backend"
uv run uvicorn main:app --host 0.0.0.0 --port "${PORT:-28080}" --timeout-graceful-shutdown 3
