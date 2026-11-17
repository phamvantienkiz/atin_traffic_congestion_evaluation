"""Entrypoint to run AIOC Staging worker directly from repository root."""

from __future__ import annotations

import sys
from pathlib import Path

INTEGRATE_ROOT = Path(__file__).resolve().parent
if str(INTEGRATE_ROOT) not in sys.path:
    sys.path.insert(0, str(INTEGRATE_ROOT))

from src.main import main

if __name__ == "__main__":
    main()
