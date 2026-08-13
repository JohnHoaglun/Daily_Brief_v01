"""
Daily Brief — Domain configuration validation rules.

Extracted from config_validator to keep the parent module ≤500 lines.
"""

from __future__ import annotations

from typing import Any

from daily_brief.config_validator import _get
from daily_brief.config_validator import _is_int
from daily_brief.config_validator import _is_non_empty_str
from daily_brief.config_validator import _looks_like_url
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# 4.  Categories
# ---------------------------------------------------------------------------


def check_categories(config: dict):
    issues: list[str] = []

    cats = config.get("categories")
    if not isinstance(cats, dict):
        issues.append("'categories' must be a dict")
        return issues
    if len(cats) == 0:
        issues.append("'categories' must have at least one entry")
        return issues

    cat_keys = set(cats.keys())

    for cname, cinfo in cats.items():
        if not isinstance(cinfo, dict):
            issues.append(f"Category '{cname}' must be a dict")
            continue
        query = cinfo.get("query")
        if not isinstance(query, str):
            issues.append(f"'categories.{cname}.query' must be a string")
        ms = cinfo.get("max_stories")
        if ms is not None:
            if not _is_int(ms):
                issues.append(f"'categories.{cname}.max_stories' must be an integer")
            elif ms < 0:
                issues.append(f"'categories.{cname}.max_stories' must be >= 0: {ms}")
        mah = cinfo.get("min_age_hours")
        if mah is not None:
            if not _is_int(mah):
                issues.append(f"'categories.{cname}.min_age_hours' must be an integer")
            elif mah <= 0 or mah > 168:
                issues.append(f"'categories.{cname}.min_age_hours' should be in (0, 168]: {mah}")
        sw = cinfo.get("source_window_hours")
        if sw is not None:
            if not _is_int(sw):
                issues.append(f"'categories.{cname}.source_window_hours' must be an integer")
            elif sw < 1 or sw > 168:
                issues.append(
                    f"'categories.{cname}.source_window_hours' should be in (0, 168]: {sw}"
                )
        dsw = _get(_get(config, "rss", {}), "default_source_window_hours")
        if dsw is not None and not _is_int(dsw):
            issues.append("'rss.default_source_window_hours' must be an integer")

        # candidate_pool_limit check (per-category, not per global rss)
        cpl = cinfo.get("candidate_pool_limit")
        if cpl is not None:
            if not _is_int(cpl):
                issues.append(f"'categories.{cname}.candidate_pool_limit' must be an integer")
            elif cpl < 1 or cpl > 500:
                issues.append(f"'categories.{cname}.candidate_pool_limit' must be in [1, 500]")

        # category_priority — every entry must exist in categories
        cp = _get(config, "category_priority", [])
        if isinstance(cp, list):
            for entry in cp:
                if entry not in cat_keys:
                    issues.append(f"'category_priority' entry '{entry}' not found in categories")

    # rss.candidate_pool_limit (global)
    rss = _get(config, "rss", {})
    if "candidate_pool_limit" in rss:
        if not _is_int(rss["candidate_pool_limit"]):
            issues.append("'rss.candidate_pool_limit' must be an integer")

    # category_boosts — keys must exist in categories
    cb = _get(config, "category_boosts", {})
    if isinstance(cb, dict):
        for bkey, bval in cb.items():
            if bkey not in cat_keys:
                issues.append(f"'category_boosts' key '{bkey}' not found in categories")
            if not isinstance(bval, list) or len(bval) == 0:
                issues.append(f"'category_boosts.{bkey}' must be a non-empty list")

    return issues


# ---------------------------------------------------------------------------
# 5.  Lake URLs
# ---------------------------------------------------------------------------


def check_lake_urls(config: dict):
    issues: list[str] = []

    lakes = _get(config, "weather.lake_urls")
    if lakes is None:
        return issues
    if not isinstance(lakes, dict) or len(lakes) == 0:
        issues.append("'weather.lake_urls' must be a non-empty dict")
        return issues
    for lname, lurl in lakes.items():
        if not _is_non_empty_str(lurl):
            issues.append(f"'weather.lake_urls.{lname}' must be a non-empty string URL")
        elif not _looks_like_url(lurl):
            issues.append(f"'weather.lake_urls.{lname}' must start with http(s): '{lurl}'")

    return issues


# ---------------------------------------------------------------------------
# 6.  Prompts
# ---------------------------------------------------------------------------


def check_prompts(config: dict):
    issues: list[str] = []

    prompts = _get(config, "prompts", {})
    if not isinstance(prompts, dict):
        issues.append("'prompts' must be a dict")
        return issues

    for pname in ("summary", "summary_strict", "system_batch"):
        val = prompts.get(pname)
        if not _is_non_empty_str(val):
            issues.append(f"'prompts.{pname}' must be a non-empty string")
        elif len(val.strip()) < 20:
            issues.append(f"'prompts.{pname}' is too short ({len(val)} chars, min 20)")

    return issues


# ---------------------------------------------------------------------------
# Batch scheduler constants validation
# ---------------------------------------------------------------------------


def check_batch_scheduler(config: dict):
    """Validate llm.summary_batch_size and llm.summary_max_concurrency from YAML."""
    issues: list[str] = []
    llm = _get(config, "llm", {})
    bs = _get(llm, "summary_batch_size")
    if bs is not None:
        if not _is_int(bs) or bs < 1:
            issues.append(f"'llm.summary_batch_size' must be an integer >= 1: {bs}")
    mc = _get(llm, "summary_max_concurrency")
    if mc is not None:
        if not _is_int(mc) or mc < 1:
            issues.append(f"'llm.summary_max_concurrency' must be an integer >= 1: {mc}")
    return issues


# ---------------------------------------------------------------------------
# 7.  Timezone & path checks
# ---------------------------------------------------------------------------


def check_timezone_and_paths(config: dict):
    issues: list[str] = []

    tz = _get(config, "runtime.timezone")
    if tz:
        try:
            ZoneInfo(tz)
        except Exception:
            issues.append(f"'runtime.timezone' is not a valid IANA timezone: '{tz}'")

    dirs = _get(config, "directories", {})
    for dk in ("log_dir", "news_dir"):
        val = _get(dirs, dk)
        if isinstance(val, str) and val and not val.startswith("/"):
            issues.append(f"'directories.{dk}' should be an absolute path: '{val}'")

    return issues
