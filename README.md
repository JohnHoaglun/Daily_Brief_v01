# Daily Brief v01 Pipeline

Automated daily news brief generator that fetches stories from 17 categories using free APIs (no keys), summarizes each with a local Ollama Qwen model, and outputs a Markdown file to Obsidian.

## Features

- **17 content categories** — World, US, Texas, Conroe TX, Montgomery County TX, Houston Tropical, Market News, Semiconductors, Big Tech, AI, OpenAI, Anthropic, SpaceX, OpenCode, Hermes Agent, Karpathy
- **Free sources only** — Google News RSS feeds + NWS weather API (no API keys, no signup)
- **Local AI summarization** — Uses `qwen3.6-256k-agents:latest` via Ollama on your hardware
- **Smart alerts** — Qwen evaluates each story for urgency; flags land in top "High-Priority Bulletins" section
- **Obsidian-native output** — Markdown with YAML frontmatter, links, bold keyword anchors

## Prerequisites

| Requirement | Why | Install |
|-------------|-----|---------|
| Python 3.9+ | Async HTTP requests, type safety | `brew install python` (macOS) or default system install |
| Ollama running with `qwen3.6-256k-agents:latest` | Summarization + alert evaluation | [ollama.com](https://ollama.com) → then `ollama pull qwen3.6-256k-agents:latest` |
| `~/.config/opencode/obsidian_vaults.md` skill (optional) | Local knowledge of Obsidian path | Already created in project setup |

## Quick Start

### Install dependencies
```bash
pip install feedparser aiohttp beautifulsoup4 ollama
```

### Run the pipeline
```bash
python dashboard_pipeline.py
```

Output file: `DailyBrief-YYYY-MM-DD__HH-MM-SS.md` → `/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/`

**Known issue**: Google News RSS feeds return snippets with embedded `<a href=...>` HTML links. The BETA02 pipeline includes `strip_html()` to handle this, but articles relying solely on RSS snippets (without article extraction) may have degraded summaries. Full article extraction is now used for all stories to compensate.

## Configuration

### Model name
In `dashboard_pipeline.py`, line ~9:
```python
QWEN_MODEL = "qwen3.6-256k-agents:latest"
```
Adjust if your model has a different tag in Ollama (`ollama list` to check).

### Output directory
Default: `/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/`
Change `OUTPUT_DIR` at the top of the script if needed.

### Weather coordinates
Default: `30.38,-95.69` (Conroe / Montgomery County area, 77316)
Change `WEATHER_LAT`, `WEATHER_LON` if you move.

## How It Works

1. **Fetch RSS feeds** — Async download 17 Google News RSS feeds + NWS weather API in parallel
2. **Extract article text** — For each story URL, download HTML → strip scripts/ads/navigation with BeautifulSoup → return first 6000 chars
3. **Summarize** — Send raw text to `ollama.chat(model=QWEN_MODEL)` with system prompt: "output exactly 2-3 sentences, factual, no pleasantries, bold 3-5 key phrases"
4. **Evaluate alerts** — Send (title + summary) to Qwen: "TRUE or FALSE if urgent alert" at temperature 0.0 for consistency
5. **Write Markdown** — Assemble with YAML frontmatter → write to obsidian vault

## Daily Workflow

1. Generate brief → `python dashboard_pipeline.py`
2. Read in Obsidian (files go directly into your vault)
3. Send brief content to AI agent manually (clipboard, file paste, or direct access)
4. Agent reads for knowledge only — no transformation needed

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|--------------|-----|
| `ModuleNotFoundError: No module named 'feedparser'` | Missing pip deps | `pip install feedparser aiohttp beautifulsoup4 ollama` |
| `Ollama is not running` or connection error | Ollama daemon down | Start Ollama app: `open -a Ollama` or `ollama serve &` |
| `model not found` | Wrong model tag | Run `ollama list`, update `QWEN_MODEL` in script |
| Feed returns zero entries | Google blocked / rate limit | Wait 10-30 min, retry. If persistent, add User-Agent header (already configured) |
| Weather API returns null periods | Bad lat/lon or API outage | Verify lat/lon, check https://api.weather.gov documentation |
| Summaries show "Summary unavailable" | RSS snippets contained embedded `<a href=...>` HTML links that passed length checks but had zero article content. BETA02 fixes: strip_html() on snippets, extract_article always runs for all stories (no length gate), 300-char minimum context for summaries |
| Articles from days ago still appear | RSS pub dates unreliable. BETA02 adds AGE_LIMIT_HOURS=24 filter in dedup loop to drop stale articles |
| Same story in multiple categories | Google News syndicates across categories. BETA02: per-category title normalization dedup prevents this |

## File Naming Convention

```
DailyBrief-YYYY-MM-DD__HH-MM-SS.md
Example: DailyBrief-2026-07-02__06-30-00.md
```

Each run creates a new file — no overwrites. Manual cleanup as needed.

## Maintaining the Pipeline

- **Update dependencies**: `pip install --upgrade feedparser aiohttp beautifulsoup4 ollama`
- **Pull latest Ollama model**: `ollama pull qwen3.6-256k-agents:latest`
- **Test individual feeds**: Set `test_categories = ["World News", "US News"]` in the script to run only a few for debugging
- **Check output quality**: Open generated `.md` files in Obsidian and spot-check summaries vs source articles

## Schedule (Future)

Currently manual. Future options:
- macOS cron: `0 6 * * * /path/to/run.sh`
- Windows Task Scheduler + batch script
- Python `schedule` library with cron-like loop

## Files

```
Daily_Brief_v01/
├── README.md               # This file — run/maintain instructions
├── PROJECT.md              # Project purpose, architecture, status
├── SUMMARY.md              # Version changelog
├── ARCHITECTURE.md         # System design doc (detailed flows)
└── dashboard_pipeline.py   # The main pipeline script
```
