#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/backend"
uv run uvicorn main:app --host 0.0.0.0 --port 8080
