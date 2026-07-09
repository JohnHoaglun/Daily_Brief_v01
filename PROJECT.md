# Daily_Brief_v01

## Purpose
Automatically generates a curated daily news brief from 17 content categories and writes a Markdown file to Obsidian. Uses free APIs (Google News RSS, NWS weather API) and local Ollama AI for summarization — no API keys required.

## Architecture

```
Input Layer          Processing Layer           Output Layer
 ┌──────────────┐    ┌───────────────────┐    ┌──────────────────┐
 │ 17 RSS feeds │───▶│ Async text fetch  │───▶│ YAML frontmatter │
 │ NWS weather  │    │ BeautifulSoup     │    │ Markdown report  │
 │              │    │ Ollama Qwen (batch)│   │ Per-category     │
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
- Ollama running on DGX Spark (http://192.168.4.52:11434) with model `qwen3.6-256k-agents:latest`
- `feedparser`, `aiohttp`, `beautifulsoup4`, `ollama` (pip install)

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

- v0.2.5: PERF: Phase 3 refactored from serial single-story processing to parallel batch fan-out (article extraction, summarization, alert evaluation all concurrent with thread pool). FIX: Alert collection now captures ALL alerts not just last story. FIX: Markdown headlines are hyperlinks [Title](URL). IMPROVED: Pub date extracted from RSS and displayed per story.
- BETA01: workers=3, timeout=180s, retry loops on _summarize()/ _evaluate_alert(). NOTE: Retry storms caused Ollama timeout cascades in first run.
- BETA02 (previous): Root cause — Google News RSS snippets contained raw `<a href=...>` HTML markup (~700-1500 chars) which passed the `len(raw)>=50` length check so `extract_article()` was NEVER called; Ollama received title+source as "context" and failed silently. Fixes: strip_html() removes `<a>` tags from snippets before length check; _summarize() minimum context raised to 300 chars; Phase 3A always runs extract_article for ALL stories (no length gate, RSS gives nothing useful); parse_feed_date() uses email.utils.parsedate_to_datetime; AGE_LIMIT_HOURS=24 with age filter in dedup loop drops stale articles; per-category title normalization dedup prevents same story from multiple sources appearing as different; StoryPipelineState replaced `snippet` slot with `pub_dt`. Pipeline is ready for end-to-end test run.
- BETA03 (current): FIX: Corrected Obsidian vault path from `Documents/Shared_AI/vault/...` to `Documents/Obsidian_Shared_AI/Shared_AI/vault/...` — the actual vault directory is named `Obsidian_Shared_AI`. CHANGED: Per-run log files now use `.md` extension (`run_log_YYYY-MM-DD__HH-MM-SS.md`) instead of `.log`, written to `vault/logs/`. Removed duplicate header banners in main(). Old non-timestamped `daily_brief.log` removed. Pipeline ready for production run.
