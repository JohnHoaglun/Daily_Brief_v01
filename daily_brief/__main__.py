"""Daily Brief — Entry Point."""

import asyncio
import sys


async def main() -> int:
    """Main entry point for the daily brief pipeline."""
    from daily_brief.pipeline import main as pipeline_main

    result = await pipeline_main()
    return result if result is not None else 0


def console_entry() -> None:
    """Synchronous entry point for the `daily-brief` console script and `python -m daily_brief`."""
    from daily_brief.cli import run as cli_run

    exit_code = cli_run()
    if exit_code is not None:
        sys.exit(exit_code)

    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    console_entry()
