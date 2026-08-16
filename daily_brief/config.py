"""
Daily Brief Configuration Loader
=================================
Single authoritative source. Loads config.yaml once at import and derives
all module-level constants from canonical YAML paths.  No globals().update().
"""

import os
from importlib import resources as importlib_resources
from pathlib import Path
from typing import Optional

import yaml

from daily_brief._version import __version__ as PACKAGE_VERSION

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_HOME = Path.home() / ".config" / "daily_brief" / "config.yaml"


# ---------------------------------------------------------------------------
# Defaults — single nested structure matching the canonical YAML shape
# ---------------------------------------------------------------------------
DEFAULTS = {
    "llm": {
        "model": "gemma4-e2b",
        "host": "http://localhost:11434/v1",
        "summary_options": {"temperature": 0.3, "top_p": 0.8},
        "context_preview_chars": 600,
        "summary_context_chars": 6000,
        "summary_trim_min_chars": 100,
        "summary_retry": {"attempts": 2, "backoff": [0.5, 1.0]},
        "summary_batch_size": 4,
        "summary_max_concurrency": 2,
    },
    "weather": {
        "lat": 30.286,
        "lon": -95.566,
        "wunderground_station_id": "KTXMONTG645",
        "wunderground_monthly_template": (
            "https://www.wunderground.com/dashboard/pws/{station_id}/graph/{date}/{date}/monthly"
        ),
        "lake_urls": {
            "conroe": "https://waterdatafortexas.org/reservoirs/individual/conroe",
            "corpus_christi": "https://waterdata.texas.org/reservoirs/individual/corpus-christi",
            "travis": "https://waterdata.texas.gov/reservoirs/individual/travis",
        },
    },
    "rss": {
        "base_url": "https://news.google.com/rss/search?q=",
        "params": "&hl=en-US&gl=US&ceid=US:en",
        "default_age_limit_hours": 24,
        "default_source_window_hours": 24,
        "candidate_pool_limit": 50,
        "dedupe_window_hours": 24,
    },
    "network": {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    },
    "runtime": {
        "timezone": "America/Chicago",
        "preflight_checks_enabled": False,
        "frontmatter_tag_segments": ["daily-intelligently", "news-summary", "ai-generated"],
        "frontmatter_fallback_tag": "#news",
        "max_log_versions": 5,
        "article_max_concurrency": 4,
    },
    "tagging_config": {"max_tags": 5, "score_cap": 5.0, "score_threshold": 0.3},
}


def _find_config_path() -> Optional[Path]:
    """Resolve config path with fallback chain: env override, project root, package default."""
    explicit = os.environ.get("DAILY_BRIEF_CONFIG")
    if explicit:
        return Path(explicit)

    project_config = BASE_DIR / "config.yaml"
    if project_config.is_file():
        return project_config

    home_config = CONFIG_HOME
    if home_config.is_file():
        return home_config

    shipped = BASE_DIR / "daily_brief" / "config.yaml"
    if shipped.is_file():
        return shipped

    return None


def _read_config_path(path: Path) -> dict:
    """Read and parse a single YAML config file."""
    if path is None:
        return _read_package_default()
    try:
        data = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(data)
        return raw if isinstance(raw, dict) else {}
    except Exception as exc:
        print(f"YAML load error ({path}): {exc}")
        return {}


def _read_package_default() -> dict:
    """Load the factory defaults shipped with the wheel."""
    try:
        cfg_bytes = importlib_resources.files("daily_brief").joinpath("config.yaml").read_bytes()
        raw = yaml.safe_load(cfg_bytes)
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def load_raw_config(yaml_path=None):
    """Return unvalidated YAML data, or an empty dict when it cannot be read.

    Resolution order:
    1. Explicit ``yaml_path`` argument
    2. ``DAILY_BRIEF_CONFIG`` environment variable
    3. ``config.yaml`` in project root (source install)
    4. ``~/.config/daily_brief/config.yaml`` (user config)
    5. Packaged ``daily_brief/config.yaml`` (wheel default)
    """
    if yaml_path is not None:
        return _read_config_path(Path(yaml_path))
    return _read_config_path(_find_config_path())


def load_config_yaml(yaml_path=None):
    """Legacy compatibility wrapper for callers that load config.yaml directly."""
    return load_raw_config(yaml_path)


_SENTINEL = object()


def _get_nested(d, path, default=_SENTINEL):
    """Extract a nested value using a dotted path eg directories.log_dir."""
    if not d:
        return default if default is not _SENTINEL else None
    parts = path.split(".")
    cur = d
    for part in parts:
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return default if default is not _SENTINEL else None
        if cur is None:
            return default if default is not _SENTINEL else None
    return cur if cur is not None else (default if default is not _SENTINEL else None)


def build_runtime_config(raw_cfg):
    """Construct typed runtime constants from validated configuration data."""
    raw_cfg = raw_cfg if isinstance(raw_cfg, dict) else {}

    def value(path, default, expected=None):
        candidate = _get_nested(raw_cfg, path, default=_SENTINEL)
        if candidate is _SENTINEL or candidate is None or not candidate:
            return default
        return candidate if expected is None or isinstance(candidate, expected) else default

    def number(path, default, conversion):
        candidate = value(path, default, (int, float))
        return conversion(candidate) if not isinstance(candidate, bool) else conversion(default)

    categories_raw = value("categories", {}, dict)
    categories = []
    category_age_limits = {}
    category_source_windows = {}
    category_candidate_pool_limits = {}
    default_window = int(number("rss.default_source_window_hours", 24, int))
    default_pool_limit = int(number("rss.candidate_pool_limit", 50, int))
    for cat_name, cat_info in categories_raw.items():
        if not isinstance(cat_info, dict):
            continue
        max_st = cat_info.get("max_stories", 10)
        max_st = int(max_st) if isinstance(max_st, int) and not isinstance(max_st, bool) else 10
        categories.append((cat_name, cat_info.get("query", ""), max_st))
        category_age_limits[cat_name] = cat_info.get("min_age_hours", 24)
        window_val = cat_info.get("source_window_hours", default_window)
        category_source_windows[cat_name] = (
            int(window_val)
            if isinstance(window_val, int) and not isinstance(window_val, bool)
            else default_window
        )
        pool_val = cat_info.get("candidate_pool_limit", default_pool_limit)
        category_candidate_pool_limits[cat_name] = (
            int(pool_val)
            if isinstance(pool_val, int) and not isinstance(pool_val, bool)
            else default_pool_limit
        )

    prompts = value("prompts", {}, dict)
    summary_options = dict(value("llm.summary_options", DEFAULTS["llm"]["summary_options"], dict))
    summary_options["temperature"] = number(
        "llm.summary_options.temperature",
        DEFAULTS["llm"]["summary_options"]["temperature"],
        float,
    )
    summary_options["top_p"] = number(
        "llm.summary_options.top_p",
        DEFAULTS["llm"]["summary_options"]["top_p"],
        float,
    )
    raw_backoff = value("llm.summary_retry.backoff", DEFAULTS["llm"]["summary_retry"]["backoff"])
    backoff_values = raw_backoff if isinstance(raw_backoff, list) else [raw_backoff]
    backoff = [
        float(delay)
        if isinstance(delay, (int, float)) and not isinstance(delay, bool)
        else float(DEFAULTS["llm"]["summary_retry"]["backoff"][0])
        for delay in backoff_values
    ]
    return {
        "VERSION": PACKAGE_VERSION,
        "LLM_MODEL": value("llm.model", DEFAULTS["llm"]["model"], str),
        "OLLAMA_HOST": value("llm.host", DEFAULTS["llm"]["host"], str),
        "LOG_DIR": value("directories.log_dir", None, str),
        "NEWS_DIR": value("directories.news_dir", None, str),
        "WEATHER_LAT": number("weather.lat", DEFAULTS["weather"]["lat"], float),
        "WEATHER_LON": number("weather.lon", DEFAULTS["weather"]["lon"], float),
        "WEATHER_POINT_URL": "https://api.weather.gov/points/{lat},{lon}",
        "WEATHER_POINT_FORECAST_SUFFIX": "forecast",
        "WEATHER_SECTION_TITLE": "Weather Forecast",
        "WEATHER_WUNDERGROUND_STATION_ID": value(
            "weather.wunderground_station_id", DEFAULTS["weather"]["wunderground_station_id"], str
        ),
        "WUNDERGROUND_MONTHLY_TEMPLATE": value(
            "weather.wunderground_monthly_template",
            DEFAULTS["weather"]["wunderground_monthly_template"],
            str,
        ),
        "WEATHER_LAKE_URLS": value("weather.lake_urls", DEFAULTS["weather"]["lake_urls"], dict),
        "RSS_BASE": value("rss.base_url", DEFAULTS["rss"]["base_url"], str),
        "RSS_PARAMS": value("rss.params", DEFAULTS["rss"]["params"], str),
        "RSS_SETTINGS": value("rss", {}, dict),
        "DEFAULT_AGE_WINDOW_HOURS": number(
            "rss.default_age_limit_hours", DEFAULTS["rss"]["default_age_limit_hours"], int
        ),
        "DEDUPE_WINDOW_HOURS": number(
            "rss.dedupe_window_hours", DEFAULTS["rss"]["dedupe_window_hours"], int
        ),
        "USER_AGENT": value("network.user_agent", DEFAULTS["network"]["user_agent"], str),
        "TIMEZONE": value("runtime.timezone", DEFAULTS["runtime"]["timezone"], str),
        "PREFLIGHT_CHECKS_ENABLED": value("runtime.preflight_checks_enabled", False, bool),
        "MAX_LOG_VERSIONS": number(
            "runtime.max_log_versions", DEFAULTS["runtime"]["max_log_versions"], int
        ),
        "ARTICLE_MAX_CONCURRENCY": number(
            "runtime.article_max_concurrency", DEFAULTS["runtime"]["article_max_concurrency"], int
        ),
        "FRONTMATTER_TAG_SEEDS": list(
            value(
                "runtime.frontmatter_tag_segments",
                DEFAULTS["runtime"]["frontmatter_tag_segments"],
                list,
            )
        ),
        "FRONTMATTER_FALLBACK_TAG": value(
            "runtime.frontmatter_fallback_tag",
            DEFAULTS["runtime"]["frontmatter_fallback_tag"],
            str,
        ),
        "LLM_SUMMARY_OPTIONS": summary_options,
        "LLM_SUMMARY_CONTEXT_CHARS": number(
            "llm.summary_context_chars", DEFAULTS["llm"]["summary_context_chars"], int
        ),
        "LLM_CONTEXT_PREVIEW_CHARS": number(
            "llm.context_preview_chars", DEFAULTS["llm"]["context_preview_chars"], int
        ),
        "LLM_SUMMARY_TRIM_MIN_CHARS": number(
            "llm.summary_trim_min_chars", DEFAULTS["llm"]["summary_trim_min_chars"], int
        ),
        "LLM_SUMMARY_RETRY_ATTEMPTS": number(
            "llm.summary_retry.attempts", DEFAULTS["llm"]["summary_retry"]["attempts"], int
        ),
        "LLM_SUMMARY_RETRY_BACKOFF": list(backoff),
        "LLM_SUMMARY_BATCH_SIZE": number(
            "llm.summary_batch_size", DEFAULTS["llm"]["summary_batch_size"], int
        ),
        "LLM_SUMMARY_MAX_CONCURRENCY": number(
            "llm.summary_max_concurrency", DEFAULTS["llm"]["summary_max_concurrency"], int
        ),
        "DATE_OVERRIDE": None,
        "CATEGORIES_RAW": categories_raw,
        "CATEGORIES": categories,
        "CATEGORY_AGE_LIMITS": category_age_limits,
        "CATEGORY_SOURCE_WINDOWS": category_source_windows,
        "CATEGORY_CANDIDATE_POOL_LIMITS": category_candidate_pool_limits,
        "RSS_CANDIDATE_POOL_LIMIT": default_pool_limit,
        "CATEGORY_AGE_LIMITS_EFFECTIVE": category_age_limits,
        "FILTERING_KEYWORDS": value("filtering_keywords", {}, dict),
        "TAGGING_MAPPINGS": value("tagging_mappings", {}, dict),
        "TAGGING_CONFIG": value("tagging_config", DEFAULTS["tagging_config"], dict),
        "CATEGORY_BOOSTS": value("category_boosts", {}, dict),
        "TAG_CONFLICTS": list(value("tag_conflicts", [], list)),
        "CATEGORY_PRIORITY": list(value("category_priority", [], list)),
        "WEATHER_LABELS": value("weather_labels", {}, dict),
        "PROMPTS": prompts,
        "SUMMARY_PROMPT": prompts.get("summary", ""),
        "SUMMARY_STRICT_PROMPT": prompts.get("summary_strict", prompts.get("summary", "")),
        "SYSTEM_BATCH_PROMPT": prompts.get("system_batch", ""),
    }


CONFIG_YAML = load_config_yaml()
_RUNTIME_CONFIG = build_runtime_config(CONFIG_YAML)

__all__ = (
    "load_raw_config",
    "load_config_yaml",
    "build_runtime_config",
    "DEFAULTS",
    "BASE_DIR",
    "CONFIG_HOME",
    "CONFIG_YAML",
    "DEFAULT_AGE_LIMIT_HOURS",
    *sorted(_RUNTIME_CONFIG.keys()),
)


def __getattr__(name: str):
    if name == "DEFAULT_AGE_LIMIT_HOURS":
        return _RUNTIME_CONFIG["DEFAULT_AGE_WINDOW_HOURS"]
    if name in _RUNTIME_CONFIG:
        return _RUNTIME_CONFIG[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
