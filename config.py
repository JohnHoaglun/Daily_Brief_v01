# Daily Brief Configuration File

import os
import ast

# Read config.txt and parse all variables with basic handling
def load_config():
    settings = {}
    
    try:
        with open("config.txt", "r") as f:
            content = f.read()
            
        for line in content.split('\n'):
            line = line.strip()
            if '=' in line and not line.startswith('#') and line.strip() != '':
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Process different types
                if value.lower() in ('null', 'none'):
                    settings[key] = None
                elif value.startswith('"') and value.endswith('"'):
                    settings[key] = value[1:-1]
                elif value == '{}':
                    settings[key] = {}
                else:
                    try:
                        # First, check if it looks like a dict/list by trying to parse it as such
                        if value.startswith('{') or value.startswith('['):
                            parsed_value = ast.literal_eval(value)
                            settings[key] = parsed_value
                        elif '.' in value:
                            settings[key] = float(value)
                        else:
                            settings[key] = int(value)
                    except (ValueError, SyntaxError):
                        settings[key] = value
                        
    except FileNotFoundError:
        print("Error: config.txt not found")
        
    return settings

# Load configuration values
config_dict = load_config()

# Extract all variables (this is a minimal approach that just uses what exists)
LLM_MODEL = config_dict.get('LLM_MODEL', 'mistral')
LOG_DIR = config_dict.get('LOG_DIR', './logs')
NEWS_DIR = config_dict.get('NEWS_DIR', './news')
MAX_VERSIONS = int(config_dict.get('MAX_VERSIONS', 5))
TIMEZONE = config_dict.get('TIMEZONE', 'America/Chicago')
OLLAMA_HOST = config_dict.get('OLLAMA_HOST', 'http://localhost:11434')
WEATHER_LAT = config_dict.get('WEATHER_LAT', '29.7604') 
WEATHER_LON = config_dict.get('WEATHER_LON', '-95.3698')

# Create directories
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(NEWS_DIR, exist_ok=True)

VERSION = config_dict.get('VERSION', '1.0.0')

MAX_STORIES_PER_CATEGORY = int(config_dict.get('MAX_STORIES_PER_CATEGORY', 10))
DEDUPE_WINDOW_HOURS = int(config_dict.get('DEDUPE_WINDOW_HOURS', 24))

RSS_BASE = config_dict.get('RSS_BASE', 'https://feeds.bbci.co.uk/news/')
RSS_PARAMS = config_dict.get('RSS_PARAMS', '?fmt=json')

# CATEGORIES - Try to parse it from config.txt as dictionary, with fallback to prevent failures
try:
    CATEGORIES_RAW = config_dict.get('CATEGORIES', {})
    
    # If the value is a string that looks like JSON/dict, try to parse it
    if isinstance(CATEGORIES_RAW, str):
        import ast
        try:
            parsed_dict = ast.literal_eval(CATEGORIES_RAW)
            if isinstance(parsed_dict, dict):
                CATEGORIES_RAW = parsed_dict
            else:
                # If it wasn't a dictionary after parsing, use fallback approach
                raise ValueError("Not a dictionary")
        except (ValueError, SyntaxError):
            # If parsing failed, we'll just fall through to the fallback approach
            pass
    
    # If we got a dictionary, transform the structure
    if isinstance(CATEGORIES_RAW, dict):
        # Transform the dictionary format to list of tuples (category_name, query, max_stories) 
        CATEGORIES = []
        for category_name, config_data in CATEGORIES_RAW.items():
            if isinstance(config_data, dict):
                query = config_data.get('query')
                max_stories = int(config_data.get('max_stories', 5))
            else:
                # If format is not a dict, assume it's just the query string (old format)  
                query = config_data
                max_stories = 5  # Default
            
            CATEGORIES.append((category_name, query, max_stories))
    elif isinstance(CATEGORIES_RAW, str) and CATEGORIES_RAW.strip() == '{}':
        # Handle case where it's just an empty dictionary 
        CATEGORIES = []
    elif isinstance(CATEGORIES_RAW, list):
        CATEGORIES = CATEGORIES_RAW
    else:
        # Handle case where it's not properly formatted - fallback to ensure we don't break the program  
        raise ValueError(f"Unexpected CATEGORIES format: {type(CATEGORIES_RAW)}")
        
except Exception as e:
    print(f"Warning: Could not parse CATEGORIES from config.txt - using fallback. Error: {e}")
    # Basic fallback to ensure we don't break the program  
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

# Make all variables available for imports
globals().update(locals())