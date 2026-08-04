"""
Daily Brief Configuration Loader
=================================
Single authoritative source. Loads config.yaml once at import and derives
all module-level constants from canonical YAML paths.  No globals().update().
"""

import os
import yaml
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Defaults — single nested structure matching the canonical YAML shape
# ---------------------------------------------------------------------------
DEFAULTS = {
    "version": "1.0.108",
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
    "directories": {
        "log_dir": "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/logs",
        "news_dir": "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/news",
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
    },
    "tagging_config": {"max_tags": 5, "score_cap": 5.0, "score_threshold": 0.3},
}


def load_config_yaml():
    """Load configuration from config.yaml using PyYAML. Returns parsed dict with all keys."""
    config_path = BASE_DIR / "config.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        print(f"Error: config.yaml not found")
        return DEFAULTS.copy()
    except Exception as exc:
        print(f"YAML load error: {exc}")
        return DEFAULTS.copy()


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


CONFIG_YAML = load_config_yaml()


# ---------------------------------------------------------------------------
# Core — single canonical YAML path per constant
# ---------------------------------------------------------------------------

# Version
VERSION = _get_nested(CONFIG_YAML, "version") or DEFAULTS["version"]

# LLM
LLM_MODEL = _get_nested(CONFIG_YAML, "llm.model") or DEFAULTS["llm"]["model"]
OLLAMA_HOST = _get_nested(CONFIG_YAML, "llm.host") or DEFAULTS["llm"]["host"]

# Directories
LOG_DIR = (
    _get_nested(CONFIG_YAML, "directories.log_dir")
    or DEFAULTS["directories"]["log_dir"]
)
NEWS_DIR = (
    _get_nested(CONFIG_YAML, "directories.news_dir")
    or DEFAULTS["directories"]["news_dir"]
)

# Weather
WEATHER_LAT = float(
    _get_nested(CONFIG_YAML, "weather.lat") or DEFAULTS["weather"]["lat"]
)
WEATHER_LON = float(
    _get_nested(CONFIG_YAML, "weather.lon") or DEFAULTS["weather"]["lon"]
)
WEATHER_POINT_URL = "https://api.weather.gov/points/{lat},{lon}"
WEATHER_POINT_FORECAST_SUFFIX = "forecast"
WEATHER_SECTION_TITLE = "Weather Forecast"
WEATHER_WUNDERGROUND_STATION_ID = (
    _get_nested(CONFIG_YAML, "weather.wunderground_station_id")
    or DEFAULTS["weather"]["wunderground_station_id"]
)
WUNDERGROUND_MONTHLY_TEMPLATE = (
    _get_nested(CONFIG_YAML, "weather.wunderground_monthly_template")
    or DEFAULTS["weather"]["wunderground_monthly_template"]
)
WEATHER_LAKE_URLS = (
    _get_nested(CONFIG_YAML, "weather.lake_urls")
    or DEFAULTS["weather"]["lake_urls"]
)

# RSS
RSS_BASE = (
    _get_nested(CONFIG_YAML, "rss.base_url") or DEFAULTS["rss"]["base_url"]
)
RSS_PARAMS = (
    _get_nested(CONFIG_YAML, "rss.params") or DEFAULTS["rss"]["params"]
)
RSS_SETTINGS = _get_nested(CONFIG_YAML, "rss") or {}
DEFAULT_AGE_WINDOW_HOURS = (
    _get_nested(CONFIG_YAML, "rss.default_age_limit_hours")
    or DEFAULTS["rss"]["default_age_limit_hours"]
)
DEDUPE_WINDOW_HOURS = (
    _get_nested(CONFIG_YAML, "rss.dedupe_window_hours")
    or DEFAULTS["rss"]["dedupe_window_hours"]
)
DEFAULT_AGE_LIMIT_HOURS = DEFAULT_AGE_WINDOW_HOURS

# Network
USER_AGENT = (
    _get_nested(CONFIG_YAML, "network.user_agent") or DEFAULTS["network"]["user_agent"]
)

# Runtime
TIMEZONE = (
    _get_nested(CONFIG_YAML, "runtime.timezone") or DEFAULTS["runtime"]["timezone"]
)

def _get_bool(cfg_path: str, default: bool) -> bool:
    """Safely read a boolean — does NOT use bool(value or False) which turns
    the string "false" into True."""
    val = _get_nested(CONFIG_YAML, cfg_path, default=_SENTINEL)
    if val is _SENTINEL:
        return default
    if not isinstance(val, bool):
        return default
    return val

PREFLIGHT_CHECKS_ENABLED = _get_bool("runtime.preflight_checks_enabled", False)
MAX_LOG_VERSIONS = int(
    _get_nested(CONFIG_YAML, "runtime.max_log_versions")
    or DEFAULTS["runtime"]["max_log_versions"]
)
FRONTMATTER_TAG_SEEDS = (
    _get_nested(CONFIG_YAML, "runtime.frontmatter_tag_segments")
    or DEFAULTS["runtime"]["frontmatter_tag_segments"]
)
FRONTMATTER_FALLBACK_TAG = (
    _get_nested(CONFIG_YAML, "runtime.frontmatter_fallback_tag")
    or DEFAULTS["runtime"]["frontmatter_fallback_tag"]
)

# LLM tuning — canonical llm.* paths only
LLM_SUMMARY_OPTIONS = (
    _get_nested(CONFIG_YAML, "llm.summary_options")
    or DEFAULTS["llm"]["summary_options"]
)
LLM_SUMMARY_CONTEXT_CHARS = int(
    _get_nested(CONFIG_YAML, "llm.summary_context_chars")
    or DEFAULTS["llm"]["summary_context_chars"]
)
LLM_CONTEXT_PREVIEW_CHARS = int(
    _get_nested(CONFIG_YAML, "llm.context_preview_chars")
    or DEFAULTS["llm"]["context_preview_chars"]
)
LLM_SUMMARY_TRIM_MIN_CHARS = int(
    _get_nested(CONFIG_YAML, "llm.summary_trim_min_chars")
    or DEFAULTS["llm"]["summary_trim_min_chars"]
)

# Summary retry
LLM_SUMMARY_RETRY_ATTEMPTS = int(
    _get_nested(CONFIG_YAML, "llm.summary_retry.attempts")
    or DEFAULTS["llm"]["summary_retry"]["attempts"]
)
LLM_SUMMARY_RETRY_BACKOFF = list(
    _get_nested(CONFIG_YAML, "llm.summary_retry.backoff")
    or DEFAULTS["llm"]["summary_retry"]["backoff"]
)

# Batch scheduler — C.2a benchmark winner (4,2): 55.6% faster than baseline (3,1)
LLM_SUMMARY_BATCH_SIZE = int(
    _get_nested(CONFIG_YAML, "llm.summary_batch_size")
    or DEFAULTS["llm"]["summary_batch_size"]
)
LLM_SUMMARY_MAX_CONCURRENCY = int(
    _get_nested(CONFIG_YAML, "llm.summary_max_concurrency")
    or DEFAULTS["llm"]["summary_max_concurrency"]
)

# Tags
DATE_OVERRIDE = None

# Categories
CATEGORIES_RAW = _get_nested(CONFIG_YAML, "categories") or {}

CATEGORIES = []
for cat_name, cat_info in CATEGORIES_RAW.items():
    query = cat_info.get("query", "")
    max_stories = cat_info.get("max_stories", 10)
    CATEGORIES.append((cat_name, query, max_stories))

# Category age limits
CATEGORY_AGE_LIMITS = {}
for cat_name, cat_info in CATEGORIES_RAW.items():
    min_age = cat_info.get("min_age_hours", 24)
    CATEGORY_AGE_LIMITS[cat_name] = min_age
CATEGORY_AGE_LIMITS_EFFECTIVE = CATEGORY_AGE_LIMITS

# Remaining config keys — no defaults required beyond YAML
FILTERING_KEYWORDS = _get_nested(CONFIG_YAML, "filtering_keywords") or {}
TAGGING_MAPPINGS = _get_nested(CONFIG_YAML, "tagging_mappings") or {}
TAGGING_CONFIG = (
    _get_nested(CONFIG_YAML, "tagging_config") or DEFAULTS["tagging_config"]
)
CATEGORY_BOOSTS = _get_nested(CONFIG_YAML, "category_boosts") or {}
TAG_CONFLICTS = _get_nested(CONFIG_YAML, "tag_conflicts") or []
CATEGORY_PRIORITY = _get_nested(CONFIG_YAML, "category_priority") or []
WEATHER_LABELS = _get_nested(CONFIG_YAML, "weather_labels") or {}

# Prompts
PROMPTS = _get_nested(CONFIG_YAML, "prompts") or {}
SUMMARY_PROMPT = PROMPTS.get("summary", "")
SUMMARY_STRICT_PROMPT = PROMPTS.get("summary_strict", SUMMARY_PROMPT)
SYSTEM_BATCH_PROMPT = PROMPTS.get("system_batch", "")
