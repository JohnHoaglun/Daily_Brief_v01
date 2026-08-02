"""
Config schema & validation for config.yaml.

Grouped validation rules: required_keys, types, ranges, categories,
lake_urls, prompts, tagging.  Runs at pipeline startup before Phase 1.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import re
from typing import Any


class ConfigValidationError(Exception):
    """Raised when config validation fails."""
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(d: dict, path: str, default: Any = None) -> Any:
    """Dot-path accessor that returns *default* on any missing key."""
    parts = path.split(".")
    cur = d
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return default
    return cur if cur is not None else default


def _is_str(v: Any) -> bool:
    return isinstance(v, str)


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_float(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_non_empty_str(v: Any) -> bool:
    return _is_str(v) and len(v.strip()) > 0


def _is_bool(v: Any) -> bool:
    return isinstance(v, bool)


def _looks_like_url(v: str) -> bool:
    return v.startswith("http://") or v.startswith("https://")


# ---------------------------------------------------------------------------
# 1.  Required keys
# ---------------------------------------------------------------------------

_REQUIRED_TOP = ["version", "llm", "directories", "weather", "categories", "prompts"]
_REQUIRED_LLM = ["model", "host"]
_REQUIRED_DIRS = ["log_dir", "news_dir"]
_REQUIRED_WEATHER = ["lat", "lon", "wunderground_station_id", "lake_urls"]
_REQUIRED_PROMPTS = ["summary", "system_batch"]


def check_required_keys(config: dict):
    issues: list[str] = []

    for key in _REQUIRED_TOP:
        if key not in config:
            issues.append(f"Missing required top-level key: '{key}'")

    llm = _get(config, "llm", {})
    if llm:
        for key in _REQUIRED_LLM:
            if key not in llm:
                issues.append(f"Missing required key: 'llm.{key}'")
    elif "llm" not in config:
        pass  # already caught

    dirs = _get(config, "directories", {})
    if dirs:
        for key in _REQUIRED_DIRS:
            if key not in dirs:
                issues.append(f"Missing required key: 'directories.{key}'")

    weather = _get(config, "weather", {})
    if weather:
        for key in _REQUIRED_WEATHER:
            if key not in weather:
                issues.append(f"Missing required key: 'weather.{key}'")

    prompts = _get(config, "prompts", {})
    if prompts:
        for key in _REQUIRED_PROMPTS:
            if key not in prompts:
                issues.append(f"Missing required key: 'prompts.{key}'")

    return issues


# ---------------------------------------------------------------------------
# 2.  Type checks
# ---------------------------------------------------------------------------

def check_types(config: dict):
    issues: list[str] = []

    # version
    v = config.get("version")
    if not _is_str(v):
        issues.append("'version' must be a non-empty string")

    # llm
    llm = _get(config, "llm", {})
    if not _is_str(_get(llm, "model")):
        issues.append("'llm.model' must be a non-empty string")
    if not _is_str(_get(llm, "host")):
        issues.append("'llm.host' must be a non-empty string")
    for opt in ("summary_options", "alert_options"):
        temp = _get(llm, f"{opt}.temperature")
        top_p = _get(llm, f"{opt}.top_p")
        if temp is not None and not _is_float(temp):
            issues.append(f"'llm.{opt}.temperature' must be a number")
        if top_p is not None and not _is_float(top_p):
            issues.append(f"'llm.{opt}.top_p' must be a number")
    for char_key in ("context_preview_chars", "summary_context_chars", "summary_trim_min_chars"):
        val = _get(llm, char_key)
        if val is not None and not _is_int(val):
            issues.append(f"'llm.{char_key}' must be an integer")

    # directories
    dirs = _get(config, "directories", {})
    for d in ("log_dir", "news_dir"):
        if not _is_str(_get(dirs, d)):
            issues.append(f"'directories.{d}' must be a non-empty string")

    # weather
    weather = _get(config, "weather", {})
    lat = _get(weather, "lat")
    lon = _get(weather, "lon")
    if lat is not None and not _is_float(lat):
        issues.append("'weather.lat' must be a number")
    if lon is not None and not _is_float(lon):
        issues.append("'weather.lon' must be a number")
    if not _is_str(_get(weather, "wunderground_station_id")):
        issues.append("'weather.wunderground_station_id' must be a string")

    # rss
    rss = _get(config, "rss", {})
    if not _is_str(_get(rss, "base_url")):
        issues.append("'rss.base_url' must be a string")
    if not _is_str(_get(rss, "params")):
        issues.append("'rss.params' must be a string")
    for int_k in ("default_age_limit_hours", "dedupe_window_hours"):
        val = _get(rss, int_k)
        if val is not None and not _is_int(val):
            issues.append(f"'rss.{int_k}' must be an integer")

    # runtime
    runtime = _get(config, "runtime", {})
    if not _is_str(_get(runtime, "timezone")):
        issues.append("'runtime.timezone' must be a string")
    ts = _get(runtime, "thread_pool_size")
    if ts is not None and not _is_int(ts):
        issues.append("'runtime.thread_pool_size' must be an integer")
    mlv = _get(runtime, "max_log_versions")
    if mlv is not None and not _is_int(mlv):
        issues.append("'runtime.max_log_versions' must be an integer")
    pfc = _get(runtime, "preflight_checks_enabled")
    if pfc is not None and not _is_bool(pfc):
        issues.append("'runtime.preflight_checks_enabled' must be a boolean")

    # cleanup
    cleanup = _get(config, "cleanup", {})
    clv = _get(cleanup, "max_log_versions")
    if clv is not None and not _is_int(clv):
        issues.append("'cleanup.max_log_versions' must be an integer")

    # categories  (must be a non-empty dict)
    cats = config.get("categories")
    if not isinstance(cats, dict):
        issues.append("'categories' must be a dict")

    # tagging_config
    tc = _get(config, "tagging_config", {})
    mt = _get(tc, "max_tags")
    if mt is not None and not _is_int(mt):
        issues.append("'tagging_config.max_tags' must be an integer")
    sc = _get(tc, "score_cap")
    if sc is not None and not _is_float(sc):
        issues.append("'tagging_config.score_cap' must be a number")
    st = _get(tc, "score_threshold")
    if st is not None and not _is_float(st):
        issues.append("'tagging_config.score_threshold' must be a number")

    # lake_urls
    lake_urls = _get(weather, "lake_urls")
    if lake_urls is not None and not isinstance(lake_urls, dict):
        issues.append("'weather.lake_urls' must be a dict")

    return issues


# ---------------------------------------------------------------------------
# 3.  Range / value checks
# ---------------------------------------------------------------------------

def check_ranges(config: dict):
    issues: list[str] = []

    # version  — must match X.Y.Z
    v = config.get("version", "")
    if _is_str(v) and not re.fullmatch(r"\d+\.\d+\.\d+", v.strip()):
        issues.append(f"'version' does not look like semver: '{v}' (expected X.Y.Z)")

    # llm.host
    host = _get(config, "llm.host")
    if host and not _looks_like_url(host):
        issues.append(f"'llm.host' must be a valid URL (starts with http): '{host}'")

    # llm.temperature 0-2, top_p 0-1
    llm = _get(config, "llm", {})
    for opt in ("summary_options", "alert_options"):
        temp = _get(llm, f"{opt}.temperature")
        if temp is not None:
            if temp < 0 or temp > 2:
                issues.append(f"'llm.{opt}.temperature' out of range [0, 2]: {temp}")
        top_p = _get(llm, f"{opt}.top_p")
        if top_p is not None:
            if top_p < 0 or top_p > 1:
                issues.append(f"'llm.{opt}.top_p' out of range [0, 1]: {top_p}")

    # llm char counts > 0
    for ck in ("context_preview_chars", "summary_context_chars", "summary_trim_min_chars"):
        val = _get(llm, ck)
        if val is not None and val <= 0:
            issues.append(f"'llm.{ck}' must be > 0: {val}")

    # weather lat/lon
    weather = _get(config, "weather", {})
    lat = _get(weather, "lat")
    lon = _get(weather, "lon")
    if lat is not None and (lat < -90 or lat > 90):
        issues.append(f"'weather.lat' out of range [-90, 90]: {lat}")
    if lon is not None and (lon < -180 or lon > 180):
        issues.append(f"'weather.lon' out of range [-180, 180]: {lon}")

    # rss hours
    rss = _get(config, "rss", {})
    for hk in ("default_age_limit_hours", "dedupe_window_hours"):
        val = _get(rss, hk)
        if val is not None and (val <= 0 or val > 168):
            issues.append(f"'rss.{hk}' should be in (0, 168]: {val}")

    # runtime
    runtime = _get(config, "runtime", {})
    ts = _get(runtime, "thread_pool_size")
    if ts is not None and ts < 1:
        issues.append(f"'runtime.thread_pool_size' must be >= 1: {ts}")
    mlv = _get(runtime, "max_log_versions")
    if mlv is not None and mlv < 1:
        issues.append(f"'runtime.max_log_versions' must be >= 1: {mlv}")

    # cleanup
    cleanup = _get(config, "cleanup", {})
    clv = _get(cleanup, "max_log_versions")
    if clv is not None and clv < 1:
        issues.append(f"'cleanup.max_log_versions' must be >= 1: {clv}")

    # tagging_config ranges
    tc = _get(config, "tagging_config", {})
    mt = _get(tc, "max_tags")
    if mt is not None and mt < 1:
        issues.append(f"'tagging_config.max_tags' must be >= 1: {mt}")
    sc = _get(tc, "score_cap")
    if sc is not None and sc <= 0:
        issues.append(f"'tagging_config.score_cap' must be > 0: {sc}")
    st = _get(tc, "score_threshold")
    if st is not None and (st < 0 or st > 1):
        issues.append(f"'tagging_config.score_threshold' must be in [0, 1]: {st}")

    # tagging_mappings — all values must be non-empty lists
    tm = _get(config, "tagging_mappings", {})
    if isinstance(tm, dict):
        for grp, words in tm.items():
            if not isinstance(words, list) or len(words) == 0:
                issues.append(f"'tagging_mappings.{grp}' must be a non-empty list")

    # tag_conflicts — list of 2-element pairs
    conflicts = _get(config, "tag_conflicts")
    if conflicts is not None:
        if not isinstance(conflicts, list):
            issues.append("'tag_conflicts' must be a list")
        else:
            for i, pair in enumerate(conflicts):
                if not isinstance(pair, list) or len(pair) != 2:
                    issues.append(f"'tag_conflicts[{i}]' must be a pair (list of 2 strings)")

    return issues


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

    # category_priority — every entry must exist in categories
    cp = _get(config, "category_priority", [])
    if isinstance(cp, list):
        for entry in cp:
            if entry not in cat_keys:
                issues.append(f"'category_priority' entry '{entry}' not found in categories")

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

    for pname in ("summary", "summary_strict", "system_batch", "system_alert"):
        val = prompts.get(pname)
        if not _is_str(val):
            issues.append(f"'prompts.{pname}' must be a non-empty string")
        elif len(val.strip()) < 20:
            issues.append(f"'prompts.{pname}' is too short ({len(val)} chars, min 20)")

    return issues


# ---------------------------------------------------------------------------
# Batch scheduler constants validation
# ---------------------------------------------------------------------------

def check_batch_scheduler(config: dict):
    """Validate LLM_SUMMARY_BATCH_SIZE and LLM_SUMMARY_MAX_CONCURRENCY from config module."""
    issues: list[str] = []

    from daily_brief.config import LLM_SUMMARY_BATCH_SIZE, LLM_SUMMARY_MAX_CONCURRENCY

    if not _is_int(LLM_SUMMARY_BATCH_SIZE) or LLM_SUMMARY_BATCH_SIZE < 1:
        issues.append(f"'LLM_SUMMARY_BATCH_SIZE' must be an integer >= 1: {LLM_SUMMARY_BATCH_SIZE}")

    if not _is_int(LLM_SUMMARY_MAX_CONCURRENCY) or LLM_SUMMARY_MAX_CONCURRENCY < 1:
        issues.append(f"'LLM_SUMMARY_MAX_CONCURRENCY' must be an integer >= 1: {LLM_SUMMARY_MAX_CONCURRENCY}")

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
        if val and not val.startswith("/"):
            issues.append(f"'directories.{dk}' should be an absolute path: '{val}'")

    return issues


# ---------------------------------------------------------------------------
# Master dispatcher
# ---------------------------------------------------------------------------

CHECK_GROUPS = [
    ("required_keys", check_required_keys),
    ("types", check_types),
    ("ranges", check_ranges),
    ("categories", check_categories),
    ("lake_urls", check_lake_urls),
    ("prompts", check_prompts),
    ("batch_scheduler", check_batch_scheduler),
    ("timezone_paths", check_timezone_and_paths),
]


def validate_config(config: dict) -> tuple[bool, list[str]]:
    """Validate *config* dict (loaded from config.yaml).

    Returns
    -------
    (passed: bool, issues: list[str])
        *passed* is ``True`` when no issues were found.
    """
    all_issues: list[str] = []
    for group_name, check_fn in CHECK_GROUPS:
        try:
            group_issues = check_fn(config)
            if group_issues:
                all_issues.extend(group_issues)
        except Exception as exc:
            all_issues.append(f"[{group_name}] internal error: {exc}")

    passed = len(all_issues) == 0
    return passed, all_issues


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import yaml
    import os
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = os.path.join(parent, "..", "config.yaml")
    with open(cfg) as f:
        data = yaml.safe_load(f)
    ok, iss = validate_config(data)
    status = "PASS" if ok else "FAIL"
    print(f"Self-test: {status} — {len(iss)} issues")
    for issue in iss:
        print(f"  ✗ {issue}")
