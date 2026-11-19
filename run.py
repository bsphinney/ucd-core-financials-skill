#!/usr/bin/env python3
"""Entry point for the ucd-core-financials skill: `python run.py <command> ...`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core_financials.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
