"""
Daily Brief v1.0.12 — Entry Point
==================================
Run the daily brief pipeline via `python -m daily_brief`.
"""

import asyncio
import logging
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


async def main() -> None:
    """Main entry point for the daily brief pipeline."""
    # Import dashboard_pipeline here to avoid circular imports at package level
    sys.path.insert(0, str(__file__).rsplit("/", 2)[0])
    from dashboard_pipeline import main as pipeline_main

    await pipeline_main()


if __name__ == "__main__":
    import config
    setup_logging(log_dir=config.LOG_DIR)
    asyncio.run(main())
