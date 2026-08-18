"""Daily Brief — Entry Point."""

import argparse
import asyncio
import sys

from daily_brief.config import use_config_path


def _parse_cli_before_import() -> argparse.Namespace:
    """Parse --config BEFORE importing any config-dependent module."""
    parser = argparse.ArgumentParser(description="Daily Brief Pipeline")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to an alternate config.yaml",
    )
    args, _ = parser.parse_known_args()
    return args


async def main(config_path_override=None) -> int:
    """Main entry point for the daily brief pipeline."""
    from daily_brief.pipeline import main as pipeline_main

    result = await pipeline_main()
    return result if result is not None else 0


def console_entry() -> None:
    """Synchronous entry point for the `daily-brief` console script and `python -m daily_brief`."""
    # Parse --config BEFORE importing config-dependent modules
    args = _parse_cli_before_import()
    if args.config:
        use_config_path(args.config)

    from daily_brief.cli import run as cli_run

    exit_code = cli_run()
    if exit_code is not None:
        sys.exit(exit_code)

    sys.exit(asyncio.run(main(config_path_override=args.config)))


if __name__ == "__main__":
    console_entry()
