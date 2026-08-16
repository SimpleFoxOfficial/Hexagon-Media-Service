#!/usr/bin/env python
"""Entry point for the frozen engine. Run directly: python engine_main.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mediadl.daemon import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
