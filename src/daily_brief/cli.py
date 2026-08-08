"""
CLI subcommands for Daily Brief configuration inspection.

Usage:
    python -m daily_brief config validate
    python -m daily_brief config show
    python -m daily_brief config list-categories
    python -m daily_brief config list-lakes
    python -m daily_brief config show-prompt <name>
    python -m daily_brief config check-connectivity
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import yaml

from daily_brief.config import (
    CONFIG_YAML,
)
from daily_brief.config_validator import validate_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daily_brief",
        description="Daily Brief — local news briefing pipeline",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- config subcommand ---
    config_parser = subparsers.add_parser("config", help="Inspect configuration")
    config_subs = config_parser.add_subparsers(dest="config_subcommand")

    config_subs.add_parser("validate", help="Validate config.yaml")
    config_subs.add_parser("show", help="Print full config as YAML")
    config_subs.add_parser(
        "list-categories", help="List categories with settings"
    )
    config_subs.add_parser("list-lakes", help="List lake monitor URLs")

    sp_parser = config_subs.add_parser(
        "show-prompt", help="Print a prompt by name"
    )
    sp_parser.add_argument(
        "name",
        choices=["summary", "summary_strict", "system_batch"],
        help="Prompt name to display",
    )
    config_subs.add_parser(
        "check-connectivity",
        help="Run pre-flight connectivity checks (LLM, RSS, Weather)",
    )

    return parser


def run(argv: list[str] | None = None) -> int | None:
    """Parse args and dispatch.

    Returns 0/1 on success/failure, or *None* to signal
    the caller that the default pipeline should run instead.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "config":
        return None

    if not args.config_subcommand:
        parser.parse_args(["config", "--help"])
        return 0

    if args.config_subcommand == "validate":
        return cmd_validate()
    if args.config_subcommand == "show":
        return cmd_show()
    if args.config_subcommand == "list-categories":
        return cmd_list_categories()
    if args.config_subcommand == "list-lakes":
        return cmd_list_lakes()
    if args.config_subcommand == "show-prompt":
        return cmd_show_prompt(args.name)
    if args.config_subcommand == "check-connectivity":
        return cmd_check_connectivity()

    return 1


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_validate() -> int:
    passed, issues = validate_config(CONFIG_YAML)
    if passed:
        print("Config validation: PASS — no issues found.")
        return 0
    print(f"Config validation: FAIL — {len(issues)} issue(s) found.")
    for issue in issues:
        print(f"  - {issue}")
    return 1


def cmd_show() -> int:
    print(yaml.dump(CONFIG_YAML, default_flow_style=False, sort_keys=False, width=120))
    return 0


def cmd_list_categories() -> int:
    cats = CONFIG_YAML.get("categories", {}) if isinstance(CONFIG_YAML, dict) else {}
    if not cats:
        print("No categories defined.")
        return 0
    print(f"{'Category':<30} {'max_stories':>12} {'min_age_hours':>14}")
    print("-" * 58)
    for name, info in cats.items():
        ms = info.get("max_stories", "-")
        mah = info.get("min_age_hours", "-")
        print(f"{name:<30} {ms:>12} {mah:>14}")
    return 0


def cmd_list_lakes() -> int:
    weather = CONFIG_YAML.get("weather", {}) if isinstance(CONFIG_YAML, dict) else {}
    lakes = weather.get("lake_urls", {}) if isinstance(weather, dict) else {}
    if not lakes:
        print("No lake URLs defined.")
        return 0
    print(f"{'Lake':<20} {'URL'}")
    print("-" * 80)
    for name, url in lakes.items():
        print(f"{name:<20} {url}")
    return 0


def cmd_show_prompt(name: str) -> int:
    prompts = CONFIG_YAML.get("prompts", {}) if isinstance(CONFIG_YAML, dict) else {}
    val = prompts.get(name) if isinstance(prompts, dict) else None
    if not val:
        print(f"Prompt '{name}' is not defined in config.", file=sys.stderr)
        return 1
    print(f"--- prompts.{name} ---")
    print(val)
    return 0


async def _cmd_check_connectivity_impl() -> int:
    from daily_brief.connectivity import run_all_checks, report
    results = await run_all_checks(timeout=5.0)
    all_ok = report(results, file=sys.stdout)
    return 0 if all_ok else 1


def cmd_check_connectivity() -> int:
    return asyncio.run(_cmd_check_connectivity_impl())
