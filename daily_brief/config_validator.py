"""
Config schema & validation for config.yaml.

Grouped validation rules: required_keys, types, ranges, categories,
lake_urls, prompts, tagging.  Runs at pipeline startup before Phase 1.
"""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo


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


def _looks_like_url(v: Any) -> bool:
    return isinstance(v, str) and (v.startswith("http://") or v.startswith("https://"))


# ---------------------------------------------------------------------------
# Re-export domain checks from separate module
# ---------------------------------------------------------------------------

from daily_brief.config_validation_rules import (
    check_categories,
    check_lake_urls,
    check_prompts,
    check_batch_scheduler,
    check_timezone_and_paths,
)

# ---------------------------------------------------------------------------
# 1.  Required keys
# ---------------------------------------------------------------------------

_REQUIRED_TOP = [
    "llm",
    "directories",
    "weather",
    "categories",
    "prompts",
    "rss",
    "network",
    "runtime",
]
_REQUIRED_LLM = ["model", "host"]
_REQUIRED_DIRS = ["log_dir", "news_dir"]
_REQUIRED_WEATHER = ["lat", "lon", "wunderground_station_id", "lake_urls"]
_REQUIRED_PROMPTS = ["summary", "system_batch"]
_REQUIRED_NETWORK = ["user_agent"]
_REQUIRED_RUNTIME = ["timezone"]


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

    netw = _get(config, "network", {})
    if netw:
        for key in _REQUIRED_NETWORK:
            if key not in netw:
                issues.append(f"Missing required key: 'network.{key}'")

    runtime = _get(config, "runtime", {})
    if runtime:
        for key in _REQUIRED_RUNTIME:
            if key not in runtime:
                issues.append(f"Missing required key: 'runtime.{key}'")

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

    # llm
    llm = _get(config, "llm", {})
    if not _is_non_empty_str(_get(llm, "model")):
        issues.append("'llm.model' must be a non-empty string")
    if not _is_non_empty_str(_get(llm, "host")):
        issues.append("'llm.host' must be a non-empty string")
    for opt in ("summary_options",):
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
    for bat_key in ("summary_batch_size", "summary_max_concurrency"):
        val = _get(llm, bat_key)
        if val is not None and not _is_int(val):
            issues.append(f"'llm.{bat_key}' must be an integer")
    retry = _get(llm, "summary_retry", {})
    att = _get(retry, "attempts")
    if att is not None and not _is_int(att):
        issues.append("'llm.summary_retry.attempts' must be an integer")
    bak = _get(retry, "backoff")
    if bak is not None:
        if isinstance(bak, list):
            for i, b in enumerate(bak):
                if not _is_float(b):
                    issues.append(f"'llm.summary_retry.backoff[{i}]' must be a number")
        elif not _is_float(bak):
            issues.append("'llm.summary_retry.backoff' must be a number")

    # network
    netw = _get(config, "network", {})
    if not _is_non_empty_str(_get(netw, "user_agent")):
        issues.append("'network.user_agent' must be a non-empty string")

    # directories
    dirs = _get(config, "directories", {})
    for d in ("log_dir", "news_dir"):
        if not _is_non_empty_str(_get(dirs, d)):
            issues.append(f"'directories.{d}' must be a non-empty string")

    # weather
    weather = _get(config, "weather", {})
    lat = _get(weather, "lat")
    lon = _get(weather, "lon")
    if lat is not None and not _is_float(lat):
        issues.append("'weather.lat' must be a float")
    if lon is not None and not _is_float(lon):
        issues.append("'weather.lon' must be a float")
    if not _is_non_empty_str(_get(weather, "wunderground_station_id")):
        issues.append("'weather.wunderground_station_id' must be a non-empty string")

    # rss
    rss = _get(config, "rss", {})
    if not _is_non_empty_str(_get(rss, "base_url")):
        issues.append("'rss.base_url' must be a non-empty string")
    if not _is_non_empty_str(_get(rss, "params")):
        issues.append("'rss.params' must be a non-empty string")
    for int_k in (
        "default_age_limit_hours",
        "dedupe_window_hours",
        "default_source_window_hours",
        "candidate_pool_limit",
    ):
        val = _get(rss, int_k)
        if val is not None and not _is_int(val):
            issues.append(f"'rss.{int_k}' must be an integer")

    # runtime
    runtime = _get(config, "runtime", {})
    if not _is_non_empty_str(_get(runtime, "timezone")):
        issues.append("'runtime.timezone' must be a non-empty string")
    ts = _get(runtime, "thread_pool_size")
    if ts is not None and not _is_int(ts):
        issues.append("'runtime.thread_pool_size' must be an integer")
    mlv = _get(runtime, "max_log_versions")
    if mlv is not None and not _is_int(mlv):
        issues.append("'runtime.max_log_versions' must be an integer")
    amc = _get(runtime, "article_max_concurrency")
    if amc is not None and not _is_int(amc):
        issues.append("'runtime.article_max_concurrency' must be an integer")
    pfc = _get(runtime, "preflight_checks_enabled")
    if pfc is not None and not _is_bool(pfc):
        issues.append("'runtime.preflight_checks_enabled' must be a boolean")

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

    def require_numeric(path: str, value: Any) -> bool:
        if value is not None and not _is_float(value):
            issues.append(f"'{path}' must be a number")
            return False
        return value is not None

    def require_int(path: str, value: Any) -> bool:
        if value is not None and not _is_int(value):
            issues.append(f"'{path}' must be an integer")
            return False
        return value is not None

    # llm.host
    host = _get(config, "llm.host")
    if host and not _looks_like_url(host):
        issues.append(f"'llm.host' must be a valid URL (starts with http): '{host}'")

    # llm.temperature 0-2, top_p 0-1
    llm = _get(config, "llm", {})
    for opt in ("summary_options",):
        temp = _get(llm, f"{opt}.temperature")
        if require_numeric(f"llm.{opt}.temperature", temp):
            if temp < 0 or temp > 2:
                issues.append(f"'llm.{opt}.temperature' out of range [0, 2]: {temp}")
        top_p = _get(llm, f"{opt}.top_p")
        if require_numeric(f"llm.{opt}.top_p", top_p):
            if top_p < 0 or top_p > 1:
                issues.append(f"'llm.{opt}.top_p' out of range [0, 1]: {top_p}")

    # llm char counts > 0
    for ck in ("context_preview_chars", "summary_context_chars", "summary_trim_min_chars"):
        val = _get(llm, ck)
        if require_int(f"llm.{ck}", val) and val <= 0:
            issues.append(f"'llm.{ck}' must be > 0: {val}")

    # llm batch/concurrency >= 1
    for bk in ("summary_batch_size", "summary_max_concurrency"):
        val = _get(llm, bk)
        if require_int(f"llm.{bk}", val) and val < 1:
            issues.append(f"'llm.{bk}' must be >= 1: {val}")

    # llm summary_retry
    retry = _get(llm, "summary_retry", {})
    att = _get(retry, "attempts")
    if require_int("llm.summary_retry.attempts", att) and att < 1:
        issues.append(f"'llm.summary_retry.attempts' must be >= 1: {att}")
    bak = _get(retry, "backoff")
    if bak is not None:
        vals = bak if isinstance(bak, list) else [bak]
        for b in vals:
            if require_numeric("llm.summary_retry.backoff", b) and (b < 0 or b > 30):
                issues.append(f"'llm.summary_retry.backoff' value out of range [0, 30]: {b}")

    # weather lat/lon
    weather = _get(config, "weather", {})
    lat = _get(weather, "lat")
    lon = _get(weather, "lon")
    if require_numeric("weather.lat", lat) and (lat < -90 or lat > 90):
        issues.append(f"'weather.lat' out of range [-90, 90]: {lat}")
    if require_numeric("weather.lon", lon) and (lon < -180 or lon > 180):
        issues.append(f"'weather.lon' out of range [-180, 180]: {lon}")

    # rss hours
    rss = _get(config, "rss", {})
    for hk in ("default_age_limit_hours", "dedupe_window_hours", "candidate_pool_limit"):
        val = _get(rss, hk)
        if hk == "candidate_pool_limit":
            if require_int(f"rss.{hk}", val) and (val < 1 or val > 500):
                issues.append(f"'rss.{hk}' should be in [1, 500]: {val}")
        else:
            if require_int(f"rss.{hk}", val) and (val <= 0 or val > 168):
                issues.append(f"'rss.{hk}' should be in (0, 168]: {val}")

    # runtime
    runtime = _get(config, "runtime", {})
    ts = _get(runtime, "thread_pool_size")
    if require_int("runtime.thread_pool_size", ts) and ts < 1:
        issues.append(f"'runtime.thread_pool_size' must be >= 1: {ts}")
    mlv = _get(runtime, "max_log_versions")
    if require_int("runtime.max_log_versions", mlv) and mlv < 1:
        issues.append(f"'runtime.max_log_versions' must be >= 1: {mlv}")
    amc = _get(runtime, "article_max_concurrency")
    if require_int("runtime.article_max_concurrency", amc) and (amc < 1 or amc > 50):
        issues.append(f"'runtime.article_max_concurrency' must be in [1, 50]: {amc}")

    # tagging_config ranges
    tc = _get(config, "tagging_config", {})
    mt = _get(tc, "max_tags")
    if require_int("tagging_config.max_tags", mt) and mt < 1:
        issues.append(f"'tagging_config.max_tags' must be >= 1: {mt}")
    sc = _get(tc, "score_cap")
    if require_numeric("tagging_config.score_cap", sc) and sc <= 0:
        issues.append(f"'tagging_config.score_cap' must be > 0: {sc}")
    st = _get(tc, "score_threshold")
    if require_numeric("tagging_config.score_threshold", st) and (st < 0 or st > 1):
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
    import os

    import yaml

    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = os.path.join(parent, "config.yaml")
    with open(cfg) as f:
        data = yaml.safe_load(f)
    ok, iss = validate_config(data)
    status = "PASS" if ok else "FAIL"
    print(f"Self-test: {status} — {len(iss)} issues")
    for issue in iss:
        print(f"  ✗ {issue}")
