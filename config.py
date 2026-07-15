# Daily Brief Configuration File

import os
import ast

def load_config():
    """Load all configuration variables from config.txt"""
    settings = {}
    
    try:
        with open("config.txt", "r") as f:
            content = f.read()
            
        # Parse line by line 
        for line in content.split('\n'):
            line = line.strip()
            if '=' in line and not line.startswith('#') and line.strip() != '':
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Process different types based on format 
                if value.lower() in ('null', 'none'):
                    settings[key] = None
                elif value.startswith('"') and value.endswith('"'):
                    settings[key] = value[1:-1]
                elif value.startswith('{') and value.endswith('}'):
                    # Handle dictionary values
                    try:
                        settings[key] = ast.literal_eval(value)
                    except:
                        settings[key] = value
                else:
                    try:
                        if '.' in value:
                            settings[key] = float(value)
                        else:
                            settings[key] = int(value)
                    except ValueError:
                        settings[key] = value
                        
    except FileNotFoundError:
        print("Error: config.txt not found")
        
    return settings

# Load configuration  
config_dict = load_config()

# Extract all variables
LLM_MODEL = config_dict.get('LLM_MODEL')
LOG_DIR = config_dict.get('LOG_DIR')  
NEWS_DIR = config_dict.get('NEWS_DIR')
MAX_VERSIONS = int(config_dict.get('MAX_VERSIONS', 5))
TIMEZONE = config_dict.get('TIMEZONE')
OLLAMA_HOST = config_dict.get('OLLAMA_HOST')
WEATHER_LAT = config_dict.get('WEATHER_LAT') 
WEATHER_LON = config_dict.get('WEATHER_LON')

# Create directories
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(NEWS_DIR, exist_ok=True)

VERSION = config_dict.get('VERSION', '1.0.0')

MAX_STORIES_PER_CATEGORY = int(config_dict.get('MAX_STORIES_PER_CATEGORY', 10))
DEDUPE_WINDOW_HOURS = int(config_dict.get('DEDUPE_WINDOW_HOURS', 24))

RSS_BASE = config_dict.get('RSS_BASE')
RSS_PARAMS = config_dict.get('RSS_PARAMS')

# CATEGORIES - read from the config file as a dictionary
# Try to parse as dictionary first, fallback to empty dict if not successful
try:
    categories_dict = config_dict.get('CATEGORIES', {})
    if isinstance(categories_dict, str):
        # If it's still a string, try to convert it
        import ast
        categories_dict = ast.literal_eval(categories_dict)
    CATEGORIES = [(cat_name, cat_info.get('query'), cat_info.get('max_stories')) 
                  for cat_name, cat_info in categories_dict.items()]
except:
    print("Warning: Could not parse CATEGORIES from config.txt. Using fallback.")
    # Convert dictionary format to tuple list structure expected
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