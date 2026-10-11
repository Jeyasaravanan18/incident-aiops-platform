"""Convenience entry point for running RAG evaluation."""

# ruff: noqa: E402

import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.run_eval import run_evaluation

if __name__ == "__main__":
    asyncio.run(run_evaluation())
