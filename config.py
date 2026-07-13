# Daily Brief Configuration File

# Extract values directly from the config.txt file 
import os
import re

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
                    # For dictionaries, keep as string and process separately 
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
LLM_MODEL = config_dict.get('LLM_MODEL', 'gemma4-e2b-64k-utility:latest')
LOG_DIR = config_dict.get('LOG_DIR', '/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/logs')  
NEWS_DIR = config_dict.get('NEWS_DIR', '/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/news')
MAX_VERSIONS = int(config_dict.get('MAX_VERSIONS', 5))
TIMEZONE = config_dict.get('TIMEZONE', 'UTC')
OLLAMA_HOST = config_dict.get('OLLAMA_HOST', 'http://192.168.4.52:11434')
WEATHER_LAT = config_dict.get('WEATHER_LAT', '30.38')
WEATHER_LON = config_dict.get('WEATHER_LON', '-95.69')

# Create required directories if they don't exist
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(NEWS_DIR, exist_ok=True)

# Version
VERSION = config_dict.get('VERSION', '1.0.0')

# Process CATEGORIES from config.txt - parse dictionary manually since it's in the file
CATEGORIES = []

# Parse CATEGORIES from the config file
category_lines = []
in_categories_block = False
with open("config.txt", "r") as f:
    content = f.read()
    
# We need to specifically look for the CATEGORIES block
for line in content.split('\n'):
    if line.strip().startswith('CATEGORIES = {'):
        in_categories_block = True
        continue
    elif in_categories_block and line.strip() == '}':
        break
    elif in_categories_block and line.strip() and not line.strip().startswith('#'):
        # Look for key-value pairs in the CATEGORIES section
        if ':' in line:
            category_name = line.split(':')[0].strip().strip('"\'')
            # Look for max_stories value 
            max_stories_match = re.search(r'"max_stories":\s*(\d+)', line)
            if max_stories_match:
                max_stories = int(max_stories_match.group(1))
                CATEGORIES.append((category_name, "", max_stories))  # query="" for now, will be populated in pipeline

# Also pull CATEGORY_SETTINGS as a dict
CATEGORY_SETTINGS = {}
category_settings_start = False
with open("config.txt", "r") as f:
    content = f.read()
    
for line in content.split('\n'):
    if line.strip().startswith('CATEGORY_SETTINGS = {'):
        category_settings_start = True
        continue
    elif category_settings_start and line.strip() == '}':
        break
    elif category_settings_start and line.strip() and not line.strip().startswith('#') and ':' in line:
        # Extract key (category name)
        if '"' in line:
            category_name_match = re.search(r'"([^"]+)"', line)
            if category_name_match:
                category_name = category_name_match.group(1)
                # Extract max_stories and min_age_hours
                max_stories_match = re.search(r'max_stories.*?(\d+)', line)
                min_age_match = re.search(r'min_age_hours.*?(\d+)', line)
                
                if max_stories_match and min_age_match:
                    max_stories = int(max_stories_match.group(1))
                    min_age = int(min_age_match.group(1))
                    CATEGORY_SETTINGS[category_name] = {"max_stories": max_stories, "min_age_hours": min_age}

MAX_STORIES_PER_CATEGORY = int(config_dict.get('MAX_STORIES_PER_CATEGORY', 10))
DEDUPE_WINDOW_HOURS = int(config_dict.get('DEDUPE_WINDOW_HOURS', 24))

# RSS Feed Settings 
RSS_BASE = config_dict.get('RSS_BASE', 'https://news.google.com/rss/search?q=')
RSS_PARAMS = config_dict.get('RSS_PARAMS', '&hl=en-US&gl=US&ceid=US:en')

# Make sure all variables are available in global namespace for module imports 
globals().update(locals())