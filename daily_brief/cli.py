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
    load_raw_config,
    config_source,
)
from daily_brief.config_validator import validate_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daily_brief",
        description="Daily Brief — local news briefing pipeline",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to an alternate config.yaml for the pipeline run",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- config subcommand ---
    config_parser = subparsers.add_parser("config", help="Inspect configuration")

    config_subs = config_parser.add_subparsers(dest="config_subcommand")

    for _sub in ("validate", "show", "list-categories", "list-lakes", "check-connectivity"):
        _s = config_subs.add_parser(_sub, help=f"{_sub.replace('-', ' ').capitalize()} config")
        _s.add_argument(
            "--yaml",
            default=None,
            help="Path to an alternate config.yaml to inspect",
        )

    sp_parser = config_subs.add_parser("show-prompt", help="Print a prompt by name")
    sp_parser.add_argument(
        "name",
        choices=["summary", "summary_strict", "system_batch"],
        help="Prompt name to display",
    )
    sp_parser.add_argument(
        "--yaml",
        default=None,
        help="Path to an alternate config.yaml to inspect",
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
        from daily_brief.config import use_config_path
        if args.config:
            use_config_path(args.config)
        return None

    if args.command == "config" and not args.config_subcommand:
        parser.parse_args(["config", "--help"])
        return 0

    if args.config_subcommand == "validate":
        return cmd_validate(args.yaml)
    if args.config_subcommand == "show":
        return cmd_show(args.yaml)
    if args.config_subcommand == "list-categories":
        return cmd_list_categories(args.yaml)
    if args.config_subcommand == "list-lakes":
        return cmd_list_lakes(args.yaml)
    if args.config_subcommand == "show-prompt":
        return cmd_show_prompt(args.name, args.yaml)
    if args.config_subcommand == "check-connectivity":
        return cmd_check_connectivity()

    return 1


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_validate(yaml_path=None) -> int:
    data = load_raw_config(yaml_path)
    passed, issues = validate_config(data)
    if passed:
        print("Config validation: PASS — no issues found.")
        return 0
    print(f"Config validation: FAIL — {len(issues)} issue(s) found.")
    for issue in issues:
        print(f"  - {issue}")
    return 1


def cmd_show(yaml_path=None) -> int:
    data = load_raw_config(yaml_path) if yaml_path else CONFIG_YAML
    src = yaml_path or config_source()
    if src:
        print(f"# Resolved from: {src}")
    print(yaml.dump(data, default_flow_style=False, sort_keys=False, width=120))
    return 0


def cmd_list_categories(yaml_path=None) -> int:
    cfg = load_raw_config(yaml_path) if yaml_path else CONFIG_YAML
    cats = cfg.get("categories", {}) if isinstance(cfg, dict) else {}
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


def cmd_list_lakes(yaml_path=None) -> int:
    cfg = load_raw_config(yaml_path) if yaml_path else CONFIG_YAML
    weather = cfg.get("weather", {}) if isinstance(cfg, dict) else {}
    lakes = weather.get("lake_urls", {}) if isinstance(weather, dict) else {}
    if not lakes:
        print("No lake URLs defined.")
        return 0
    print(f"{'Lake':<20} {'URL'}")
    print("-" * 80)
    for name, url in lakes.items():
        print(f"{name:<20} {url}")
    return 0


def cmd_show_prompt(name: str, yaml_path=None) -> int:
    cfg = load_raw_config(yaml_path) if yaml_path else CONFIG_YAML
    prompts = cfg.get("prompts", {}) if isinstance(cfg, dict) else {}
    val = prompts.get(name) if isinstance(prompts, dict) else None
    if not val:
        print(f"Prompt '{name}' is not defined in config.", file=sys.stderr)
        return 1
    if yaml_path:
        print(f"# From: {yaml_path}\n")
    print(f"--- prompts.{name} ---")
    print(val)
    return 0


async def _cmd_check_connectivity_impl() -> int:
    from daily_brief.connectivity import report, run_all_checks

    results = await run_all_checks(timeout=5.0)
    all_ok = report(results, file=sys.stdout)
    return 0 if all_ok else 1


def cmd_check_connectivity() -> int:
    return asyncio.run(_cmd_check_connectivity_impl())
