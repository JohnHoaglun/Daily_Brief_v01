"""
Daily Brief Configuration Loader
=================================
Single authoritative source. Loads config.yaml once at import and derives
all module-level constants from canonical YAML paths.  No globals().update().
"""

import os
import yaml
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Defaults — single nested structure matching the canonical YAML shape
# ---------------------------------------------------------------------------
DEFAULTS = {
    "version": "1.0.133",
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


def load_raw_config(yaml_path=None):
    """Return unvalidated YAML data, or an empty dict when it cannot be read."""
    config_path = Path(yaml_path) if yaml_path is not None else Path(
        os.environ.get("DAILY_BRIEF_CONFIG", BASE_DIR / "config.yaml")
    )
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            raw_config = yaml.safe_load(fh)
            return raw_config if isinstance(raw_config, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(f"YAML load error: {exc}")
        return {}


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
    for cat_name, cat_info in categories_raw.items():
        if not isinstance(cat_info, dict):
            continue
        categories.append((cat_name, cat_info.get("query", ""), cat_info.get("max_stories", 10)))
        category_age_limits[cat_name] = cat_info.get("min_age_hours", 24)

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
        float(delay) if isinstance(delay, (int, float)) and not isinstance(delay, bool) else float(DEFAULTS["llm"]["summary_retry"]["backoff"][0])
        for delay in backoff_values
    ]
    return {
        "VERSION": value("version", DEFAULTS["version"], str),
        "LLM_MODEL": value("llm.model", DEFAULTS["llm"]["model"], str),
        "OLLAMA_HOST": value("llm.host", DEFAULTS["llm"]["host"], str),
        "LOG_DIR": value("directories.log_dir", None, str),
        "NEWS_DIR": value("directories.news_dir", None, str),
        "WEATHER_LAT": number("weather.lat", DEFAULTS["weather"]["lat"], float),
        "WEATHER_LON": number("weather.lon", DEFAULTS["weather"]["lon"], float),
        "WEATHER_POINT_URL": "https://api.weather.gov/points/{lat},{lon}",
        "WEATHER_POINT_FORECAST_SUFFIX": "forecast",
        "WEATHER_SECTION_TITLE": "Weather Forecast",
        "WEATHER_WUNDERGROUND_STATION_ID": value("weather.wunderground_station_id", DEFAULTS["weather"]["wunderground_station_id"], str),
        "WUNDERGROUND_MONTHLY_TEMPLATE": value("weather.wunderground_monthly_template", DEFAULTS["weather"]["wunderground_monthly_template"], str),
        "WEATHER_LAKE_URLS": value("weather.lake_urls", DEFAULTS["weather"]["lake_urls"], dict),
        "RSS_BASE": value("rss.base_url", DEFAULTS["rss"]["base_url"], str),
        "RSS_PARAMS": value("rss.params", DEFAULTS["rss"]["params"], str),
        "RSS_SETTINGS": value("rss", {}, dict),
        "DEFAULT_AGE_WINDOW_HOURS": number("rss.default_age_limit_hours", DEFAULTS["rss"]["default_age_limit_hours"], int),
        "DEDUPE_WINDOW_HOURS": number("rss.dedupe_window_hours", DEFAULTS["rss"]["dedupe_window_hours"], int),
        "USER_AGENT": value("network.user_agent", DEFAULTS["network"]["user_agent"], str),
        "TIMEZONE": value("runtime.timezone", DEFAULTS["runtime"]["timezone"], str),
        "PREFLIGHT_CHECKS_ENABLED": value("runtime.preflight_checks_enabled", False, bool),
        "MAX_LOG_VERSIONS": number("runtime.max_log_versions", DEFAULTS["runtime"]["max_log_versions"], int),
        "ARTICLE_MAX_CONCURRENCY": number("runtime.article_max_concurrency", DEFAULTS["runtime"]["article_max_concurrency"], int),
        "FRONTMATTER_TAG_SEEDS": list(value("runtime.frontmatter_tag_segments", DEFAULTS["runtime"]["frontmatter_tag_segments"], list)),
        "FRONTMATTER_FALLBACK_TAG": value("runtime.frontmatter_fallback_tag", DEFAULTS["runtime"]["frontmatter_fallback_tag"], str),
        "LLM_SUMMARY_OPTIONS": summary_options,
        "LLM_SUMMARY_CONTEXT_CHARS": number("llm.summary_context_chars", DEFAULTS["llm"]["summary_context_chars"], int),
        "LLM_CONTEXT_PREVIEW_CHARS": number("llm.context_preview_chars", DEFAULTS["llm"]["context_preview_chars"], int),
        "LLM_SUMMARY_TRIM_MIN_CHARS": number("llm.summary_trim_min_chars", DEFAULTS["llm"]["summary_trim_min_chars"], int),
        "LLM_SUMMARY_RETRY_ATTEMPTS": number("llm.summary_retry.attempts", DEFAULTS["llm"]["summary_retry"]["attempts"], int),
        "LLM_SUMMARY_RETRY_BACKOFF": list(backoff),
        "LLM_SUMMARY_BATCH_SIZE": number("llm.summary_batch_size", DEFAULTS["llm"]["summary_batch_size"], int),
        "LLM_SUMMARY_MAX_CONCURRENCY": number("llm.summary_max_concurrency", DEFAULTS["llm"]["summary_max_concurrency"], int),
        "DATE_OVERRIDE": None,
        "CATEGORIES_RAW": categories_raw,
        "CATEGORIES": categories,
        "CATEGORY_AGE_LIMITS": category_age_limits,
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
VERSION = _RUNTIME_CONFIG["VERSION"]
LLM_MODEL = _RUNTIME_CONFIG["LLM_MODEL"]
OLLAMA_HOST = _RUNTIME_CONFIG["OLLAMA_HOST"]
LOG_DIR = _RUNTIME_CONFIG["LOG_DIR"]
NEWS_DIR = _RUNTIME_CONFIG["NEWS_DIR"]
WEATHER_LAT = _RUNTIME_CONFIG["WEATHER_LAT"]
WEATHER_LON = _RUNTIME_CONFIG["WEATHER_LON"]
WEATHER_POINT_URL = _RUNTIME_CONFIG["WEATHER_POINT_URL"]
WEATHER_POINT_FORECAST_SUFFIX = _RUNTIME_CONFIG["WEATHER_POINT_FORECAST_SUFFIX"]
WEATHER_SECTION_TITLE = _RUNTIME_CONFIG["WEATHER_SECTION_TITLE"]
WEATHER_WUNDERGROUND_STATION_ID = _RUNTIME_CONFIG["WEATHER_WUNDERGROUND_STATION_ID"]
WUNDERGROUND_MONTHLY_TEMPLATE = _RUNTIME_CONFIG["WUNDERGROUND_MONTHLY_TEMPLATE"]
WEATHER_LAKE_URLS = _RUNTIME_CONFIG["WEATHER_LAKE_URLS"]
RSS_BASE = _RUNTIME_CONFIG["RSS_BASE"]
RSS_PARAMS = _RUNTIME_CONFIG["RSS_PARAMS"]
RSS_SETTINGS = _RUNTIME_CONFIG["RSS_SETTINGS"]
DEFAULT_AGE_WINDOW_HOURS = _RUNTIME_CONFIG["DEFAULT_AGE_WINDOW_HOURS"]
DEDUPE_WINDOW_HOURS = _RUNTIME_CONFIG["DEDUPE_WINDOW_HOURS"]
DEFAULT_AGE_LIMIT_HOURS = DEFAULT_AGE_WINDOW_HOURS
USER_AGENT = _RUNTIME_CONFIG["USER_AGENT"]
TIMEZONE = _RUNTIME_CONFIG["TIMEZONE"]
PREFLIGHT_CHECKS_ENABLED = _RUNTIME_CONFIG["PREFLIGHT_CHECKS_ENABLED"]
MAX_LOG_VERSIONS = _RUNTIME_CONFIG["MAX_LOG_VERSIONS"]
ARTICLE_MAX_CONCURRENCY = _RUNTIME_CONFIG["ARTICLE_MAX_CONCURRENCY"]
FRONTMATTER_TAG_SEEDS = _RUNTIME_CONFIG["FRONTMATTER_TAG_SEEDS"]
FRONTMATTER_FALLBACK_TAG = _RUNTIME_CONFIG["FRONTMATTER_FALLBACK_TAG"]
LLM_SUMMARY_OPTIONS = _RUNTIME_CONFIG["LLM_SUMMARY_OPTIONS"]
LLM_SUMMARY_CONTEXT_CHARS = _RUNTIME_CONFIG["LLM_SUMMARY_CONTEXT_CHARS"]
LLM_CONTEXT_PREVIEW_CHARS = _RUNTIME_CONFIG["LLM_CONTEXT_PREVIEW_CHARS"]
LLM_SUMMARY_TRIM_MIN_CHARS = _RUNTIME_CONFIG["LLM_SUMMARY_TRIM_MIN_CHARS"]
LLM_SUMMARY_RETRY_ATTEMPTS = _RUNTIME_CONFIG["LLM_SUMMARY_RETRY_ATTEMPTS"]
LLM_SUMMARY_RETRY_BACKOFF = _RUNTIME_CONFIG["LLM_SUMMARY_RETRY_BACKOFF"]
LLM_SUMMARY_BATCH_SIZE = _RUNTIME_CONFIG["LLM_SUMMARY_BATCH_SIZE"]
LLM_SUMMARY_MAX_CONCURRENCY = _RUNTIME_CONFIG["LLM_SUMMARY_MAX_CONCURRENCY"]
DATE_OVERRIDE = _RUNTIME_CONFIG["DATE_OVERRIDE"]
CATEGORIES_RAW = _RUNTIME_CONFIG["CATEGORIES_RAW"]
CATEGORIES = _RUNTIME_CONFIG["CATEGORIES"]
CATEGORY_AGE_LIMITS = _RUNTIME_CONFIG["CATEGORY_AGE_LIMITS"]
CATEGORY_AGE_LIMITS_EFFECTIVE = _RUNTIME_CONFIG["CATEGORY_AGE_LIMITS_EFFECTIVE"]
FILTERING_KEYWORDS = _RUNTIME_CONFIG["FILTERING_KEYWORDS"]
TAGGING_MAPPINGS = _RUNTIME_CONFIG["TAGGING_MAPPINGS"]
TAGGING_CONFIG = _RUNTIME_CONFIG["TAGGING_CONFIG"]
CATEGORY_BOOSTS = _RUNTIME_CONFIG["CATEGORY_BOOSTS"]
TAG_CONFLICTS = _RUNTIME_CONFIG["TAG_CONFLICTS"]
CATEGORY_PRIORITY = _RUNTIME_CONFIG["CATEGORY_PRIORITY"]
WEATHER_LABELS = _RUNTIME_CONFIG["WEATHER_LABELS"]
PROMPTS = _RUNTIME_CONFIG["PROMPTS"]
SUMMARY_PROMPT = _RUNTIME_CONFIG["SUMMARY_PROMPT"]
SUMMARY_STRICT_PROMPT = _RUNTIME_CONFIG["SUMMARY_STRICT_PROMPT"]
SYSTEM_BATCH_PROMPT = _RUNTIME_CONFIG["SYSTEM_BATCH_PROMPT"]
