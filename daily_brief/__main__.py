"""
Daily Brief v1.0.133 — Entry Point
===================================
Run the daily brief pipeline via `python -m daily_brief`.
"""

import asyncio
import sys


async def main() -> int:
    """Main entry point for the daily brief pipeline."""
    from daily_brief.pipeline import main as pipeline_main

    result = await pipeline_main()
    return result if result is not None else 0


if __name__ == "__main__":
    from daily_brief.cli import run as cli_run

    exit_code = cli_run()
    if exit_code is not None:
        sys.exit(exit_code)

    sys.exit(asyncio.run(main()))
