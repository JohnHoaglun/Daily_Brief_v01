# Daily Brief Configuration File

# Extract values directly from the config.txt file 
import os
import re
import json

# Load config manually to get all values needed for the configuration
def load_config_from_txt():
    """Load configuration directly from config.txt"""
    settings = {}
    
    try:
        with open("config.txt", "r") as f:
            content = f.read()
            
        # Parse line by line  
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Handle different value types
                if value.lower() == 'null' or value.lower() == 'none':
                    settings[key] = None
                elif value.startswith('"') and value.endswith('"'):
                    settings[key] = value[1:-1]
                elif value.startswith('{') and value.endswith('}'):
                    # For dictionaries, we'll process separately to preserve structure
                    settings[key] = value
                else:
                    # Try numeric conversion first, otherwise treat as string
                    try:
                        if '.' in value:
                            settings[key] = float(value)
                        else:
                            settings[key] = int(value)
                    except ValueError:
                        settings[key] = value
                        
    except FileNotFoundError:
        print("Config file config.txt not found")
        
    return settings

# Load everything we need
config_dict = load_config_from_txt()

# Standard configuration values  
LLM_MODEL = config_dict.get('LLM_MODEL')
LOG_DIR = config_dict.get('LOG_DIR')  
NEWS_DIR = config_dict.get('NEWS_DIR')
MAX_VERSIONS = int(config_dict.get('MAX_VERSIONS'))
TIMEZONE = config_dict.get('TIMEZONE')
OLLAMA_HOST = config_dict.get('OLLAMA_HOST')
WEATHER_LAT = config_dict.get('WEATHER_LAT')
WEATHER_LON = config_dict.get('WEATHER_LON')

# Create required directories if they don't exist
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(NEWS_DIR, exist_ok=True)

# Version
VERSION = config_dict.get('VERSION')

# Process CATEGORIES manually since the dict parsing is complex - copy from config.txt directly
CATEGORIES = [
    ("World News", "world news", 10),
    ("US News", "us news", 10),
    ("Texas News", "Texas news", 5),
    ("Conroe TX News", "Conroe TX", 5),
    ("Montgomery County TX News", "Montgomery County TX", 5),
    ("Weather Forecast 77316", "", 0),  # Special case - uses NWS API
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

# Category settings from config
CATEGORY_SETTINGS = {
    "World News": {"max_stories": 10, "min_age_hours": 24},
    "US News": {"max_stories": 10, "min_age_hours": 24},
    "Texas News": {"max_stories": 5, "min_age_hours": 24},
    "Conroe TX News": {"max_stories": 5, "min_age_hours": 24},
    "Montgomery County TX News": {"max_stories": 5, "min_age_hours": 24},
    "Weather Forecast 77316": {"max_stories": 1, "min_age_hours": 8},
    "Houston Tropical Weather": {"max_stories": 1, "min_age_hours": 24},
    "Market News": {"max_stories": 5, "min_age_hours": 24},
    "Semiconductors": {"max_stories": 5, "min_age_hours": 24},
    "Big Tech": {"max_stories": 5, "min_age_hours": 24},
    "Artificial Intelligence": {"max_stories": 5, "min_age_hours": 24},
    "OpenAI News": {"max_stories": 5, "min_age_hours": 24},
    "Anthropic News": {"max_stories": 5, "min_age_hours": 24},
    "SpaceX News": {"max_stories": 5, "min_age_hours": 24},
    "Andrej Karpathy Activity": {"max_stories": 5, "min_age_hours": 24},
    "Hermes Agent News": {"max_stories": 5, "min_age_hours": 24}
}

MAX_STORIES_PER_CATEGORY = int(config_dict.get('MAX_STORIES_PER_CATEGORY'))
DEDUPE_WINDOW_HOURS = int(config_dict.get('DEDUPE_WINDOW_HOURS'))

# RSS Feed Settings 
RSS_BASE = config_dict.get('RSS_BASE')
RSS_PARAMS = config_dict.get('RSS_PARAMS')

# Make sure all variables are available in global namespace for module imports 
globals().update(locals())