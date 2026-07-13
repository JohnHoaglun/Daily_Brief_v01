# Daily_Brief_v01

## Purpose
Automatically generates a curated daily news brief from 17 content categories and writes a Markdown file to Obsidian. Uses free APIs (Google News RSS, NWS weather API) and local Ollama AI for summarization — no API keys required.

## Architecture

```
Input Layer          Processing Layer           Output Layer
 ┌──────────────┐    ┌───────────────────┐    ┌──────────────────┐
 │ 17 RSS feeds │───▶│ Async text fetch  │───▶│ YAML frontmatter │
 │ NWS weather  │    │ BeautifulSoup     │    │ Markdown report  │
 │              │    │ gemma4:e2b (batch) │   │ Per-category     │
 │              │    │ Alert evaluator   │    │ stories          │
 └──────────────┘    └───────────────────┘    └──────────────────┘
```

## Data Sources

| Source | Type | Auth Required | URL Pattern |
|--------|------|---------------|-------------|
| Google News | RSS Feed | No | `https://news.google.com/rss/search?q=<query>&hl=en-US&gl=US&ceid=US:en` |
| NWS Weather API | JSON | No | `https://api.weather.gov/points/<lat>,<lon>` |

## Dependencies

- Python 3.9+ — runs on Mac Studio
- Ollama running on DGX Spark (http://192.168.4.52:11434) with model `gemma4:e2b`
- `feedparser`, `aiohttp`, `beautifulsoup4`, `ollama`, `playwright` (pip install)

## Output

- Files written to the Obsidian vault: `/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/`
- Logs written to: `/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/logs/run_log_YYYY-MM-DD__HH-MM-SS.md` (unique per run, `.md` format)
- Format: `DailyBrief-YYYY-MM-DD__HH-MM-SS.md`
- 17 content categories — each story has headline (hyperlinked), link, 2-3 sentence factual summary, source attribution, published date, and tags
- High-priority alerts bubbled to top section when Qwen evaluates as TRUE

## How It Runs

```bash
# From this directory
python dashboard_pipeline.py
```

## Categories (17)

| # | Category | Feed Query |
|---|----------|------------|
| 1 | World News | `world news` |
| 2 | US News | `us news` |
| 3 | Texas News | `Texas news` |
| 4 | Conroe TX News | `Conroe TX` |
| 5 | Montgomery County TX News | `Montgomery County TX` |
| 6 | Weather Forecast 77316 | NWS API (lat/lon `30.38,-95.69`) |
| 7 | Houston Tropical Weather | `Houston hurricane tropical storm` |
| 8 | Market News | `stock market economy` |
| 9 | Semiconductors | `semiconductor chips industry` |
| 10 | Big Tech | `"big tech"` |
| 11 | Artificial Intelligence | `artificial intelligence LLM generative AI` |
| 12 | OpenAI News | `OpenAI announcements` |
| 13 | Anthropic News | `Anthropic Claude AI` |
| 14 | SpaceX News | `SpaceX launch Starship` |
| 15 | OpenCode News | `OpenCode agent CLI` |
| 16 | Hermes Agent News | `Hermes Agent AI` |
| 17 | Andrej Karpathy Activity | `Andrej Karpathy AI` |

## Current Status

- v1.0.1: Fixed configuration loading issues and improved robustness. 
- Version has been tagged and committed to git repository.
