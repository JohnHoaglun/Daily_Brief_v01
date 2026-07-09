# Daily Brief Pipeline — Architecture Document

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       DAILY BRIEF PIPELINE                               │
│                                                                         │
│   ┌──────────────┐    ┌─────────────────────────────┐    ┌────────────┐│
│   │  INPUT        │    │  PROCESSING                 │    │ OUTPUT     ││
│   │              │    │                             │    │            ││
│   │ 17 × RSS Feeds│───▶│ Async HTTP Fetch            │───▶│            ││
│   │             │    │ BeautifulSoup HTML Cleaning │───▶│ Markdown   ││
│   │ NWS Weather │    │ Ollama Qwen Summarization   │    │ Report     ││
│   │               │    │ Qwen Alert Evaluator       │    │ Obsidian   ││
│   └──────────────┘    └─────────────────────────────┘    └────────────┘│
│                                                                         │
│   All via free, keyless sources. Local AI only. No paid APIs.           │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Step 1: RSS INGEST (Concurrent)
┌─────────────────────────────────────────────┐
│ For each of 17 categories:                  │
│   - Build Google News RSS URL               │
│   - aiohttp fetch (async, 8s timeout)       │
│   - Parse XML with feedparser               │
│   - strip_html() removes <a> tags from snippets │
│   - Store: title, link, pub date (pub_dt)   │
└─────────────────────────────────────────────┘

Note: RSS snippets contain raw `<a href=...>` HTML links. Without stripping, the markup passes length checks (~700-1500 chars) but yields no real article text when sent to Ollama.

Step 2: ARTICLE EXTRACTION (Concurrent per batch)
┌─────────────────────────────────────────────┐
│ For each story URL:                         │
│   - aiohttp GET with User-Agent header      │
│   - BeautifulSoup DOM parsing               │
│   - Extract <p>, <h1>, <h2>, <h3> text     │
│   - Strip scripts, nav, footer, ads         │
│   - Return first 6000 chars of clean text   │
└─────────────────────────────────────────────┘

Step 3: QWEN SUMMARIZATION (Sequential)
┌─────────────────────────────────────────────┐
│ For each extracted article:                 │
│   ├─ System prompt: "2-3 sentences, factual,"│
│   │  "bold 3-5 key phrases"                 │
│   ├─ ollama.chat(model=qwen3.6...)          │
│   └─ Temp=0.15                              │
└─────────────────────────────────────────────┘

Step 4: ALERT EVALUATION (Sequential)
┌─────────────────────────────────────────────┐
│ For each summary:                           │
│   ├─ System prompt: "TRUE/FALSE urgent?"    │
│   ├─ Criteria: weather, breakthroughs,      │
│   │  macro crises                           │
│   └─ Temp=0.0 (pure logic)                  │
└─────────────────────────────────────────────┘

Step 5: RENDER (Sequential)
┌─────────────────────────────────────────────┐
│ Assemble markdown file:                     │
│   ├─ YAML frontmatter                       │
│   ├─ High-Priority Bulletins (if alerts)    │
│   ├─ 17 category sections                  │
│   └─ Per story: headline + link, summary,   │
│     source attr, tags                       │
│ Write to Obsidian vault                     │
└─────────────────────────────────────────────┘
```

## Component Detail

### Feed Manifest

Each category maps to a Google News RSS search query:

| Category | Google News Query | Max Stories |
|----------|-------------------|-------------|
| World News | `world+news` | 10 |
| US News | `US+news` | 10 |
| Texas News | `Texas+news` | 5 |
| Conroe TX | `Conroe+TX` | 5 |
| Montgomery County TX | `Montgomery+County+TX` | 5 |
| Houston Tropical | `Houston+hurricane+tropical` | 5 |
| Market News | `stock+market+economy` | 5 |
| Semiconductors | `semiconductor+chip+industry` | 5 |
| Big Tech | `"Big+Tech"` | 5 |
| AI (LLM/GenAI) | `artificial+intelligence+generative+AI` | 5 |
| OpenAI | `OpenAI+announcements` | 5 |
| Anthropic | `Anthropic+ChatGPT` | 5 |
| SpaceX | `SpaceX+launch` | 5 |
| OpenCode | `opencode+ai+agent` | 5 |
| Hermes Agent | `"Hermes Agent"+AI` | 5 |
| Andrej Karpathy | `Andrej+Karpathy+AI` | 5 |

Note: RSS URLs are URL-encoded versions of these queries.

### NWS Weather API

```python
# Lat/Lon for 77316 (Conroe/Montgomery area)
LAT = 30.38
LON = -95.69

# Step 1: Get foreground forecast
GET https://api.weather.gov/points/{lat},{lon}

# Step 2: Parse response → properties.forecast
# Extract first 3 forecast periods (next ~1-3 days)
```

### Ollama API Calls

**Summarization Prompt:**
```yaml
System: |
  You are an objective news processing engine. Strip away website 
  formatting noise, ads and links. Analyze the remaining core text,
  and synthesize it into exactly 2 or 3 sentences in a single 
  paragraph. Be factual. No pleasantries or meta-commentary.

  Format critical words/phrases (company names, tech terms, locations, 
  metrics, action verbs) as **bold** anchors — bold exactly 3 to 5 
  key concepts.
User: Summarize this text:\n\n{extracted_text[:6000]}
```

**Alert Evaluation Prompt:**
```yaml
System: |
  You are a news priority classifier. Judge if a story warrants
  immediate attention based on these criteria:

  1. Extreme weather: hurricanes, tornadoes, flooding, freeze — 
     especially Houston/Texas/77316 threats
  2. Major tech breakthroughs from OpenAI, Anthropic, SpaceX, 
     OpenCode, or Hermes Agents
  3. Critical infrastructure crises, macroeconomic disruption, or 
     geopolitical instability

Respond with exactly ONE word: "TRUE" or "FALSE". Nothing else.
User: Headline: {title}\nSummary: {summary}
```

### Error Handling

| Failure | Behavior | Fallback |
|---------|----------|----------|
| RSS feed empty/no entries | Section prints "No active entries discovered" | Continue to next category |
| HTTP timeout (8s) | Skip that URL, log warning, continue | Next URL in batch |
| Article too short (<150 chars) | Return error summary, don't call Ollama | `Summary unavailable: article text too short` |
| Ollama connection failed | Return error string, don't crash pipeline | `Summary unavailable: AI service unavailable` |
| NWS API fails | Section header still created with fallback msg | `Weather node currently unresponsive` |

No single failure should halt the entire pipeline. Each component is isolated.

### Memory / GPU Constraints

- RSS fetches are async — network-bound, no CPU pressure
- Ollama calls use 3 parallel workers via ThreadPoolExecutor, matching NUM_PARALLEL=3 constraint on the Ollama server to avoid GPU contention
- With article extraction enabled (all stories always extracted), expect higher network/CPU during Phase 3A
- Article text capped at 6000 chars before LLM call
- Temperature: 0.15 for summaries (balanced creativity/factuality), 0.0 for alerts (exact logic)

### Output Architecture

```markdown
---
title: Daily Brief
date: YYYY-MM-DD
time_generated: ISO8601
status: active
content_age_window: 24 hours
story_count_total: N
categories: 17
---

# Daily Brief — DD Mon YYYY

## High-Priority Bulletins (if alerts found)

Each flagged story with 🚨, category context, summary

---

## World News Headlines

1. **[Headline](url)**
   Factual summary with **bold anchors**
   *Source: ... | Tags: #... | Location: ...*

---

(Repeat for all 17 categories)
```

### File Lifecycle

1. Generate → write new file to Obsidian vault path
2. Each run increments timestamp — files never overwrite
3. Manual deletion (no auto-archival per spec)

### Deployment Options (Future Phase)

Phase 1 (current): Manual `python dashboard_pipeline.py`
Phase 2: Scheduled via one of:
  - **Cron** (macOS/Linux) — most reliable, system-level scheduling
  - **Python schedule library** — keep script running as daemon
  - **Task Scheduler** (Windows) — GUI-based scheduling
