#!/usr/bin/env python3
"""
Daily Brief v1.0.146 — Supported launcher
Run: python3 dashboard_pipeline.py
"""
import asyncio
import sys

from daily_brief.pipeline import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
