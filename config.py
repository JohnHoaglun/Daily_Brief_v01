# Daily Brief Configuration File

import os

LLM_MODEL = "gemma4-e2b-64k-utility:latest"
LOG_DIR = "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/logs"
NEWS_DIR = "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/news"
MAX_VERSIONS = 5

# Create required directories if they don't exist
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(NEWS_DIR, exist_ok=True)