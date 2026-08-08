"""
Daily Brief v1.0.12 — Entry Point
==================================
Run the daily brief pipeline via `python -m daily_brief`.
"""

import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def setup_logging(log_dir: str = ".", verbose: bool = False) -> None:
    """Configure standard logging with rotating file handler."""
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.setLevel(level)

    # File handler
    os.makedirs(log_dir, exist_ok=True)
    log_file = f"{log_dir}/daily_brief.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    logging.basicConfig(level=level, handlers=[console, file_handler], force=True)


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

    from daily_brief.config import LOG_DIR

    setup_logging(log_dir=LOG_DIR)
    sys.exit(asyncio.run(main()))
