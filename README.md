# Daily Brief v1.0.1

## Overview

Daily Brief is an automated news aggregation and summarization system that collects articles from various sources, synthesizes them into concise summaries, and formats them into a daily markdown report.

## Features

- Automated RSS feed collection from Google News
- Cross-category duplicate detection and filtering  
- Article content extraction and summarization using LLM
- Time-based filtering (last 24 hours by default)
- Clean markdown output with category separation
- Automatic cleanup of old reports and logs
- Weather data integration

### New Features in v1.0.1

1. **Configuration System** - Moved all settings to config.py for easier management  
2. **Enhanced Date/Time Handling** - Shows full date+time instead of just date
3. **Cleaner Output Formatting** - Removed H3 headers, uses numbered lists instead
4. **Improved Cleanup Logic** - Maintains only MAX_VERSIONS (5) most recent files
5. **Removed Alert System** - Alerts no longer displayed in output to reduce clutter
6. **Enhanced Article Extraction** - Better handling of external URLs
7. **Configuration Loading Fix** - Resolved circular import issue causing errors

## Requirements

- Python 3.9+
- Ollama server available at http://192.168.4.52:11434 (customizable)
- Required models:
  - gemma4:e2b (or specified in config.py)
  - [additional models as needed]

## Setup

1. Install required packages: `pip install aiohttp feedparser beautifulsoup4 ollama`
2. Ensure Ollama server is running
3. Set up `config.py` with your preferences
4. Run the script with your installed Python:

```powershell
.\run_daily_brief.bat
```

If your Python path is different, replace with your local path.

If tzdata is missing in that Python install, timezone fallback is handled to UTC in code, and you can optionally install tzdata:

```powershell
C:\Users\john\AppData\Local\Python\bin\python.exe -m pip install tzdata
```

## Configuration

All configuration now resides in `config.py`. Key settings include:

- `LLM_MODEL`: The model to use for summarization  
- `LOG_DIR`: Directory for log files
- `NEWS_DIR`: Directory for output markdown files
- `MAX_VERSIONS`: Maximum number of old files to keep (default 5)

## Usage

Run the pipeline with:
`.\run_daily_brief.bat`

The script will:
1. Collect news from RSS feeds
2. Filter and deduplicate stories  
3. Extract full article content
4. Generate summaries using LLM
5. Create markdown report with clean formatting
6. Clean up old log and report files

## Output Format

Generated markdown files in `news/` directory named like `DailyBrief-2026-07-12_v01.md`

Each file includes:
- Title and metadata
- Category sections with stories listed as numbered items  
- Clean separation between categories using horizontal rules
- Full date+time formatting for all posts

## Files

```
dashboard_pipeline.py     # Main pipeline script
config.py                 # Configuration settings
requirements.txt          # Dependencies (if needed)
README.md                 # This file
news/                     # Output directory for reports  
logs/                     # Log file directory
```

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/your-feature`
3. Commit changes: `git commit -am 'Add new feature'`  
4. Push to branch: `git push origin feature/your-feature`
5. Create pull request

## License

MIT License
