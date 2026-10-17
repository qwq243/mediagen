#!/usr/bin/env python3
"""Backward-compatible wrapper. Prefer init_ppt_image_job.py --profile dense."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from init_ppt_image_job import main  # noqa: E402


if __name__ == "__main__":
    argv = list(sys.argv[1:])
    if "--profile" not in argv:
        argv = ["--profile", "dense", *argv]
    raise SystemExit(main(argv))
