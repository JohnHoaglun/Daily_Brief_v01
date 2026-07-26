import os
import yaml
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

DEFAULTS = {
    "version": "1.0.12",
    "llm_model": "gemma4-e2b",
    "ollama_host": "http://localhost:11434/v1",
    "directories": {
        "log_dir": "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/logs",  
        "news_dir": "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/news",   
    }
}

def load_config_yaml():
    """Load configuration from config.yaml using PyYAML. Returns parsed dict with all keys.""" 
    config_path = BASE_DIR / "config.yaml"
    try: 
        with open(config_path, 'r', encoding='utf-8') as filehandle:
            return yaml.safe_load(filehandle) or {}
    except FileNotFoundError:
        print(f"Error: config.yaml not found")
        return DEFAULTS
    except Exception as exc:
        print(f"YAML load error: {exc}")
        return DEFAULTS

CONFIG_YAML = load_config_yaml()

def _get_nested(d, path):
    """Extract a nested value using a dotted path eg directories.log_dir."""
    if not d: return None
    parts = path.split('.')
    for part in parts:
        if isinstance(d, dict) and part in d:
            d = d[part]
        else:
            return None
    return d

LLM_MODEL = _get_nested(CONFIG_YAML, 'llm.model') or DEFAULTS['llm_model']
OLLAMA_HOST = _get_nested(CONFIG_YAML, 'llm.host') or DEFAULTS['ollama_host']
LOG_DIR = _get_nested(CONFIG_YAML, 'directories.log_dir') or DEFAULTS['directories']['log_dir']
NEWS_DIR = _get_nested(CONFIG_YAML, 'directories.news_dir') or DEFAULTS['directories']['news_dir']

VERSION = _get_nested(CONFIG_YAML, 'version') or DEFAULTS['version']
WEATHER_LAT = float(_get_nested(CONFIG_YAML, 'weather.lat') or 30.286)
WEATHER_LON = float(_get_nested(CONFIG_YAML, 'weather.lon') or -95.566)

# Fixed: Template string for dynamic injection
WEATHER_POINT_URL = "https://api.weather.gov/points/{lat},{lon}"
WEATHER_POINT_FORECAST_SUFFIX = "forecast"
WEATHER_SECTION_TITLE = "Weather Forecast"

RSS_BASE = _get_nested(CONFIG_YAML, 'rss.base_url') or 'https://news.google.com/rss/search?q='
RSS_PARAMS = _get_nested(CONFIG_YAML, 'rss.params') or '&hl=en-US&gl=US&ceid=US:en'
TIMEZONE = _get_nested(CONFIG_YAML, 'timezone') or 'America/Chicago'

USER_AGENT = _get_nested(CONFIG_YAML, 'user_agent') or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
USER_AGENT_WEATHER_SUFFIX = _get_nested(CONFIG_YAML, 'user_agent_weather_suffix') or "/DailyBrief/1.0"

MAX_LOG_VERSIONS = _get_nested(CONFIG_YAML, 'cleanup_api.max_log_versions') or 5
FRONTMATTER_TAG_SEEDS = _get_nested(CONFIG_YAML, 'runtime_defaults.frontmatter_tag_seeds') or ["daily-brief", "news-summary", "ai-generated"]
FRONTMATTER_FALLBACK_TAG = _get_nested(CONFIG_YAML, 'runtime_defaults.frontmatter_fallback_tag') or "#news"

LLM_SUMMARY_CONTEXT_CHARS = _get_nested(CONFIG_YAML, 'runtime_defaults.llm_summary_context_chars') or 6000
LLM_CONTEXT_PREVIEW_CHARS = _get_nested(CONFIG_YAML, 'runtime_defaults.llm_context_preview_chars') or 600
LLM_SUMMARY_TRIM_MIN_CHARS = _get_nested(CONFIG_YAML, 'runtime_defaults.llm_summary_trim_min_chars') or 100

LLM_SUMMARY_OPTIONS = _get_nested(CONFIG_YAML, 'runtime_defaults.llm_summary_options') or {"temperature": 0.3, "top_p": 0.8}
LLM_ALERT_OPTIONS = _get_nested(CONFIG_YAML, 'runtime_defaults.llm_alert_options') or {"temperature": 0.1, "top_p": 0.3}

# Category definitions
CATEGORIES_RAW = _get_nested(CONFIG_YAML, 'categories') or {}
CATEGORY_SETTINGS = _get_nested(CONFIG_YAML, 'category_settings') or {}

# Build CATEGORIES as list of tuples for compatibility with existing codebase (name, query, max_stories)
CATEGORIES = []
for cat_name, cat_info in CATEGORIES_RAW.items():
    query = cat_info.get('query', '')
    max_stories = cat_info.get('max_stories', 10)
    CATEGORIES.append((cat_name, query, max_stories))

# Category age limits
CATEGORY_AGE_LIMITS = {}
for cat_name, cat_info in CATEGORIES_RAW.items():
    min_age = 24 # default
    if 'min_age_hours' in cat_info:
        min_age = cat_info['min_age_hours']
    elif 'category_settings' in CONFIG_YAML and cat_name in _get_nested(CONFIG_YAML, 'category_settings'):
        pass 
    CATEGORY_AGE_LIMITS[cat_name] = min_age
# Create a compatibility alias for the pipeline which expects CATEGORY_AGE_LIMITS_EFFECTIVE
CATEGORY_AGE_LIMITS_EFFECTIVE = CATEGORY_AGE_LIMITS

# RSS and Filtering configuration from yaml
RSS_SETTINGS = _get_nested(CONFIG_YAML, 'rss_settings') or {}
DEFAULT_AGE_WINDOW_HOURS = RSS_SETTINGS.get('default_age_window_hours', 24)
DEDUPE_WINDOW_HOURS = RSS_SETTINGS.get('dedupi_window_hours', 24)
DEFAULT_AGE_LIMIT_HOURS = RSS_SETTINGS.get('default_age_limit_hours', 24)

FILTERING_KEYWORDS = _get_nested(CONFIG_YAML, 'filtering_keywords') or {}
REAL_ESTATE_KEYWORDS = FILTERING_KEYWORDS.get('real_estate', [])
OBITUARY_KEYWORDS = FILTERING_KEYWORDS.get('obituary', [])

TAGGING_MAPPINGS = _get_nested(CONFIG_YAML, 'tagging_mappings') or {}
CATEGORY_PRIORITY = _get_nested(CONFIG_YAML, 'category_priority') or []
WEATHER_LABELS = _get_nested(CONFIG_YAML, 'weather_labels') or {}


# Prompts
PROMPTS = _get_nested(CONFIG_YAML, 'prompts') or {}
SUMMARY_PROMPT = PROMPTS.get('summary', '')
SYSTEM_BATCH_PROMPT = PROMPTS.get('system_batch', '')
SYSTEM_ALERT_PROMPT = PROMPTS.get('system_alert', '')

# Weather infrastructure
WEATHER_WUNDERGROUND_STATION_ID = _get_nested(CONFIG_YAML, 'weather.wunderground_station_id') or "KTXMONTG645"
WUNDERGROUND_MONTHLY_TEMPLATE = _get_nested(CONFIG_YAML, 'weather.wunderground_monthly_template') or "https://www.wunderground.com/dashboard/pws/{station_id}/graph/{date}/{date}/monthly"
WEATHER_LAKE_URLS = _get_nested(CONFIG_YAML, 'weather.lake_urls') or {
    "conroe": "https://waterdatafortexas.org/reservoirs/individual/conroe",
    "corpus_christi": "https://waterdata.texas.org/reservoirs/individual/corpus-christi",
    "travis": "https://waterdata.texas.gov/reservoirs/individual/travis"
}
# Fixed: This is now a template string
WEATHER_POINT_URL = "https://api.weather.to/points/{lat},{lon}" 
# (Wait, the previous error showed api.weather.gov... I will correct it to the real one)
WEATHER_POINT_URL = "https://api.weather.gov/points/{lat},{lon}"

DATE_OVERRIDE = None

# Universe of constants for the pipeline
globals().update(locals())

