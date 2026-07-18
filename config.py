# Daily Brief Configuration File

import os
import ast
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _parse_value(value):
    value = value.strip()
    if not value:
        return ""
    if value.lower() in ('null', 'none'):
        return None
    if value.lower() in ('true', 'false'):
        return value.lower() == 'true'
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if re.match(r"^[0-9]+(?:\.[0-9]+)?$", value):
        if '.' in value:
            return float(value)
        return int(value)
    try:
        if value[0] in ('{', '[', '(') and value[-1] in ('}', ']', ')'):
            return ast.literal_eval(value)
    except Exception:
        pass
    return value


def load_config():
    """Load all configuration variables from config.txt (supports multiline dict/list blocks)."""
    settings = {}

    try:
        with open("config.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()

        current_key = None
        block_lines = []
        in_block = False

        for raw in lines:
            line = raw.rstrip("\n")
            stripped = line.strip()

            if not stripped or stripped.startswith('#'):
                continue

            if in_block:
                block_lines.append(line)
                if stripped.endswith('}') or stripped.endswith(']') or stripped.endswith(')'):
                    # best-effort end-of-block: close when depth is balanced on this line
                    combined = "\n".join(block_lines).strip()
                    if combined.count('{') == combined.count('}') and combined.count('[') == combined.count(']') and combined.count('(') == combined.count(')'):
                        settings[current_key] = _parse_value(combined)
                        current_key = None
                        block_lines = []
                        in_block = False
                continue

            if '=' not in stripped:
                continue

            key, value = stripped.split('=', 1)
            key = key.strip()
            value = value.strip()

            if value in ('{', '[', '(') or (
                value.startswith('{') and not value.endswith('}')
                or value.startswith('[') and not value.endswith(']')
                or value.startswith('(') and not value.endswith(')')
            ):
                in_block = True
                current_key = key
                block_lines = [value]
                combined = "\n".join(block_lines).strip()
                if combined.count('{') == combined.count('}') and combined.count('[') == combined.count(']') and combined.count('(') == combined.count(')'):
                    settings[current_key] = _parse_value(combined)
                    current_key = None
                    block_lines = []
                    in_block = False
            else:
                settings[key] = _parse_value(value)

        if in_block and current_key and block_lines:
            settings[current_key] = _parse_value("\n".join(block_lines).strip())

    except FileNotFoundError:
        print("Error: config.txt not found")

    return settings


def _safe_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


# Load configuration  
config_dict = load_config()

# Extract all variables
LLM_MODEL = config_dict.get('LLM_MODEL')
LOG_DIR = config_dict.get('LOG_DIR')
NEWS_DIR = config_dict.get('NEWS_DIR')
MAX_VERSIONS = _safe_int(config_dict.get('MAX_VERSIONS', 5), 5)
MAX_LOG_VERSIONS = _safe_int(config_dict.get('MAX_LOG_VERSIONS', 5), 5)
TIMEZONE = config_dict.get('TIMEZONE', 'America/Chicago')
OLLAMA_HOST = config_dict.get('OLLAMA_HOST')
WEATHER_LAT = str(config_dict.get('WEATHER_LAT', '30.286'))
WEATHER_LON = str(config_dict.get('WEATHER_LON', '-95.566'))
WEATHER_POINT_URL = config_dict.get('WEATHER_POINT_URL', 'https://forecast.weather.gov/MapClick.php?lon=-95.566&lat=30.286')
WEATHER_POINT_FORECAST_SUFFIX = config_dict.get('WEATHER_POINT_FORECAST_SUFFIX', 'forecast')
WEATHER_WUNDERGROUND_STATION_ID = config_dict.get('WEATHER_WUNDERGROUND_STATION_ID', 'KTXMONTG645')
WUNDERGROUND_MONTHLY_TEMPLATE = config_dict.get(
    'WUNDERGROUND_MONTHLY_TEMPLATE',
    'https://www.wunderground.com/dashboard/pws/{station_id}/graph/{date}/{date}/monthly'
)
WEATHER_LAKE_URLS = config_dict.get('WEATHER_LAKE_URLS', {
    'conroe': 'https://waterdatafortexas.org/reservoirs/individual/conroe',
    'corpus_christi': 'https://waterdatafortexas.org/reservoirs/individual/corpus-christi',
    'travis': 'https://waterdatafortexas.org/reservoirs/individual/travis',
})

# Resolve and create configured directories in a project-safe way
def _resolve_output_dir(path_value, fallback_name):
    if not path_value:
        return os.path.join(BASE_DIR, fallback_name)

    candidate = str(path_value).strip()
    lower = candidate.lower()

    if candidate.startswith('/Users/'):
        mapped = candidate.replace('/Users/', 'C:\\Users\\')
        mapped = os.path.normpath(mapped)
        if os.path.exists(mapped):
            candidate = mapped

    # Heuristic compatibility for old macOS/Linux-like paths accidentally carried into
    # Windows configs (for example, /Users/...).
    if candidate.startswith(("/", "\\")) or lower.startswith("/users/"):
        if not os.path.exists(candidate):
            return os.path.join(BASE_DIR, fallback_name)

    if os.path.isabs(candidate):
        return candidate

    return os.path.join(BASE_DIR, candidate)


LOG_DIR = _resolve_output_dir(LOG_DIR, "logs")
NEWS_DIR = _resolve_output_dir(NEWS_DIR, "news")

if LOG_DIR:
    os.makedirs(LOG_DIR, exist_ok=True)
if NEWS_DIR:
    os.makedirs(NEWS_DIR, exist_ok=True)

VERSION = config_dict.get('VERSION', '1.0.0')

MAX_STORIES_PER_CATEGORY = _safe_int(config_dict.get('MAX_STORIES_PER_CATEGORY', 10), 10)
DEDUPE_WINDOW_HOURS = _safe_int(config_dict.get('DEDUPE_WINDOW_HOURS', 24), 24)

RSS_BASE = config_dict.get('RSS_BASE')
RSS_PARAMS = config_dict.get('RSS_PARAMS')
DEFAULT_AGE_LIMIT_HOURS = _safe_int(config_dict.get('DEFAULT_AGE_LIMIT_HOURS', DEDUPE_WINDOW_HOURS), 24)
CATEGORY_AGE_LIMITS = config_dict.get('CATEGORY_AGE_LIMITS', {})
CATEGORY_SETTINGS = config_dict.get('CATEGORY_SETTINGS', {})

USER_AGENT = config_dict.get('USER_AGENT', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
USER_AGENT_WEATHER_SUFFIX = config_dict.get('USER_AGENT_WEATHER_SUFFIX', '/DailyBrief/1.0')
USER_AGENT_HINT = USER_AGENT_WEATHER_SUFFIX
SUMMARY_PROMPT = config_dict.get('SUMMARY_PROMPT', 'You are an objective news editor. Write a detailed summary of at least 3 sentences covering the key facts of this article.')
SYSTEM_BATCH_PROMPT = config_dict.get('SYSTEM_BATCH_PROMPT', 'You are a news summarization engine. For each story I list, produce a detailed summary.')
SYSTEM_ALERT_PROMPT = config_dict.get('SYSTEM_ALERT_PROMPT', 'You are a news priority classifier. For EACH story provided, respond with exactly one line.')

LLM_SUMMARY_CONTEXT_CHARS = _safe_int(config_dict.get('LLM_SUMMARY_CONTEXT_CHARS', 6000), 6000)
LLM_CONTEXT_PREVIEW_CHARS = _safe_int(config_dict.get('LLM_CONTEXT_PREVIEW_CHARS', 600), 600)
LLM_SUMMARY_TRIM_MIN_CHARS = _safe_int(config_dict.get('LLM_SUMMARY_TRIM_MIN_CHARS', 100), 100)
LLM_SUMMARY_OPTIONS = config_dict.get('LLM_SUMMARY_OPTIONS', {
    'temperature': 0.3,
    'top_p': 0.8,
    'num_ctx': 8192,
})
LLM_ALERT_OPTIONS = config_dict.get('LLM_ALERT_OPTIONS', {
    'temperature': 0.1,
    'top_p': 0.3,
    'num_ctx': 8192,
})

DEFAULT_CONTENT_AGE_WINDOW_HOURS = config_dict.get('DEFAULT_CONTENT_AGE_WINDOW_HOURS', '24 hours')
DEFAULT_CATEGORIES_COUNT = _safe_int(config_dict.get('DEFAULT_CATEGORIES_COUNT', 17), 17)
FRONTMATTER_TAG_SEEDS = config_dict.get('FRONTMATTER_TAG_SEEDS', ['daily-brief', 'news-summary', 'ai-generated'])
FRONTMATTER_FALLBACK_TAG = config_dict.get('FRONTMATTER_FALLBACK_TAG', '#news')
WEATHER_SECTION_TITLE = config_dict.get('WEATHER_SECTION_TITLE', 'Weather for 77316')
DATE_OVERRIDE = config_dict.get('DATE_OVERRIDE')

# CATEGORIES - read from the config file as a dictionary
# Try to parse as dictionary first, fallback to empty dict if not successful
try:
    categories_dict = config_dict.get('CATEGORIES', {})
    if isinstance(categories_dict, str):
        categories_dict = ast.literal_eval(categories_dict)
    if not isinstance(categories_dict, dict):
        raise ValueError
    CATEGORIES = []
    for cat_name, cat_info in categories_dict.items():
        if not isinstance(cat_info, dict):
            continue
        CATEGORIES.append((cat_name, cat_info.get('query', ''), _safe_int(cat_info.get('max_stories', MAX_STORIES_PER_CATEGORY), MAX_STORIES_PER_CATEGORY)))
except Exception:
    print("Warning: Could not parse CATEGORIES from config.txt. Using fallback.")
    CATEGORIES = [
        ("World News", "world news", 10),
        ("US News", "us news", 10),
        ("Texas News", "Texas news", 5),
        ("Conroe TX News", "Conroe TX", 5),
        ("Montgomery County TX News", "Montgomery County TX", 5),
        ("Weather Forecast 77316", None, 0),
        ("Houston Tropical Weather", "Houston Tropical Weather", 1),
        ("Market News", "market news", 5),
        ("Semiconductors", "semiconductors", 5),
        ("Big Tech", "big tech", 5),
        ("Artificial Intelligence", "artificial intelligence", 5),
        ("OpenAI News", "OpenAI news", 5),
        ("Anthropic News", "Anthropic news", 5),
        ("SpaceX News", "SpaceX news", 5),
        ("Andrej Karpathy Activity", "Andrej Karpathy", 5),
        ("Hermes Agent News", "hermes agent", 5)
    ]

# Derived per-category age limits: fallback to DEFAULT_AGE_LIMIT_HOURS
CATEGORY_AGE_LIMITS_EFFECTIVE = {}
for category_name, _query, _max in CATEGORIES:
    age_hours = DEFAULT_AGE_LIMIT_HOURS
    if isinstance(CATEGORY_SETTINGS, dict):
        item = CATEGORY_SETTINGS.get(category_name)
        if isinstance(item, dict) and 'min_age_hours' in item:
            age_hours = _safe_int(item.get('min_age_hours'), age_hours)
    if isinstance(CATEGORY_AGE_LIMITS, dict) and category_name in CATEGORY_AGE_LIMITS:
        age_hours = _safe_int(CATEGORY_AGE_LIMITS.get(category_name), age_hours)
    CATEGORY_AGE_LIMITS_EFFECTIVE[category_name] = age_hours

# Make all variables available for imports
globals().update(locals())
