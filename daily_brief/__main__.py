"""Daily Brief — Entry Point."""

import argparse
import asyncio
import sys


async def main(config_path_override=None) -> int:
    """Main entry point for the daily brief pipeline."""
    from daily_brief.pipeline import main as pipeline_main
    from daily_brief.config import use_config_path

    if config_path_override:
        use_config_path(config_path_override)

    result = await pipeline_main()
    return result if result is not None else 0


def console_entry() -> None:
    """Synchronous entry point for the `daily-brief` console script and `python -m daily_brief`."""
    from daily_brief.cli import run as cli_run

    exit_code = cli_run()
    if exit_code is not None:
        sys.exit(exit_code)

    # Parse CLI flags for the main pipeline
    parser = argparse.ArgumentParser(description="Daily Brief Pipeline")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to an alternate config.yaml",
    )
    args, _ = parser.parse_known_args()

    sys.exit(asyncio.run(main(config_path_override=args.config)))


if __name__ == "__main__":
    console_entry()
