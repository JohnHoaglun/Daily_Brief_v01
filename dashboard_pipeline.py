#!/usr/bin/env python3
"""
Daily Brief Pipeline — Thin shim (v1.0.36)
All code lives in src/daily_brief/ subpackages.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from daily_brief.pipeline import main

if __name__ == "__main__":
    asyncio.run(main())
