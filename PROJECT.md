# Daily_Brief_v01

## Purpose
Automatically generates a curated daily news brief from 17 content categories and writes a Markdown file to Obsidian. Uses free APIs (Google News RSS, NWS weather API) and local Ollama AI for summarization — no API keys required.

## Architecture

```
Input Layer          Processing Layer           Output Layer
 ┌──────────────┐    ┌───────────────────┐    ┌──────────────────┐
 │ 17 RSS feeds │───▶│ Async text fetch  │───▶│ YAML frontmatter │
 │ NWS weather  │   │ BeautifulSoup     │    │ Markdown report  │
 │                │   │ Ollama Qwen       │    │ Per-category     │
 │                │   │ Alert evaluator   │    │ stories          │
└──────────────┘    └───────────────────┘    └──────────────────┘
```

## Data Sources

| Source | Type | Auth Required | URL Pattern |
|--------|------|---------------|-------------|
| Google News | RSS Feed | No | `https://news.google.com/rss/search?q=<query>&hl=en-US&gl=US&ceid=US:en` |
| NWS Weather API | JSON | No | `https://api.weather.gov/points/<lat>,<lon>` |

## Dependencies

- Python 3.9+
- Ollama running locally with model `qwen3.6-256k-agents:latest`
- `feedparser`, `aiohttp`, `beautifulsoup4`, `ollama` (pip install)

## Output

- Files written to the Obsidian vault: `/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/`
- Format: `DailyBrief-YYYY-MM-DD__HH-MM-SS.md`
- 17 content categories (see spec) — each story has headline, link, 2-3 sentence factual summary, source attribution, and tags
- High-priority alerts bubbled to a top section when Qwen evaluates as TRUE

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

- v0.0.1: Initial pipeline scaffold — async fetching, Ollama summarization, alert routing, Markdown output with YAML frontmatter
