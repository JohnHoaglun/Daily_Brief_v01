# Daily Brief Pipeline — Validation Test Harness

**Purpose:** Run this checklist against every `run_log_*.md` + `DailyBrief-*.md` pair before trusting the output. Designed to be scriptable — each check below states what to read, what to compute, and the pass/warn/fail threshold.

**Inputs required per run:**
- `run_log_YYYY-MM-DD_vNN.md` (pipeline log)
- `DailyBrief-YYYY-MM-DD_vNN.md` (rendered output)
- `config.yaml` (same directory as the main pipeline script — defines desired per-category story counts, feed list, etc.)

**Path resolution:** `directories.log_dir` and `directories.news_dir` in `config.yaml` are the source of truth for where the log and output files actually live — these currently point to `.../Daily_Brief_v01/Dev/logs` and `.../Dev/news`, but will differ for a Prod run. The harness must read these paths from `config.yaml` at execution time rather than hardcoding either environment. If you're validating a Prod run, make sure you're pointing the harness at the Prod `config.yaml`, not Dev's.

**Status levels:** `PASS` / `WARN` (log it, don't block) / `FAIL` (run needs human review before use)

---

## Phase 1 — Weather Data

| # | Check | Method | Threshold |
|---|---|---|---|
| 1.1 | Forecast periods fetched | Parse log line `Weather forecast periods fetched: N` | FAIL if N < 3 |
| 1.2 | Forecast rows rendered | Count rows in the 3-day forecast table in output | FAIL if ≠ 3 (unless config specifies a different window) |
| 1.3 | Station data present | Log contains `[fetch_weather] Station data complete` with non-null `avg_temp_today`, `avg_monthly_rainfall`, `current_monthly_rainfall` | FAIL if any field is `None`/missing |
| 1.4 | Lake data completeness | All configured lakes (from `config.yaml`) have a `today` + `1 week ago` + `30 days ago` row in output table | WARN if 1 lake missing, FAIL if >1 missing |
| 1.5 | Sane value ranges | Air temps (forecast high/low, climate normal high, avg_temp_today): 20–115°F for 77316. Precip % 0–100. Lake fill % 0–100 | FAIL if any value outside range — for air temp fields specifically, anything >115°F is not real weather (see F.4 for the known elevation-mis-source cause) |
| 1.6 | Phase 1 timing | Log `Phase 1 completed in Xs` | WARN if X > 30s |

---

## Phase 2 — RSS Feed Fetch

### 2.0 Expected per-category count — source of truth
`config.yaml` (same directory as the main pipeline script) is the **source of truth** — every category and its `max` value originates there. The log's `[DEBUG] Categories being fetched` block is what the running process actually loaded, and should be an exact reflection of `config.yaml` for that run.

- Parse both: `config.yaml`'s category list + max values, and the log block's category list + `(max: N)` values.
- **FAIL** if they don't match — a mismatch means `config.yaml` was edited but the pipeline is running on a stale/cached config, or a category was dropped/altered somewhere between config load and the fetch call. This is a config-loading bug, not just informational drift.
- Once matched, use these `max: N` values for all downstream count checks (2.3, 3.1).

| # | Check | Method | Threshold |
|---|---|---|---|
| 2.1 | All configured categories fetched | Compare category list in log's `[DEBUG] Categories being fetched` block against `config.yaml` category list | FAIL if any configured category is missing entirely |
| 2.2 | Zero-result categories | Any category with 0 stories fetched *before* dedup | See 2.2a — this now ties to the adaptive widening spec below rather than being treated as simple informational noise |
| 2.3 | Raw fetch count sane, per category | Compare each category's raw fetched count (from `Feed results by category` block) against its `max: N` from 2.0 | WARN if a category's raw count is 0 while its configured max is >0; FAIL if total raw stories across all categories is 0 |
| 2.4 | Dedup ratio sane | `(pre_dedup - post_dedup) / pre_dedup` | WARN if dedup removes >40% of stories (possible over-aggressive matching) or 0% across a 50+ story run (dedup likely not running) |
| 2.5 | Phase 2 timing | Log `Phase 2 completed in Xs` | WARN if X > 10s |

### 2.6 Known bug — RSS query string typo ("Hermes Agent News")
`config.yaml`'s `categories."Hermes Agent News".query` is currently `"herms agent"` — missing the "e" in Hermes. This is almost certainly the real cause of that category returning 0 stories every run, separate from (and likely masking the need for) the adaptive widening feature in 2.2a.

- **FAIL** if `categories."Hermes Agent News".query` != `"hermes agent"` (case-insensitive) — this is a known, named bug with a known fix, not a general typo-detection rule.
- More generally: if any category returns 0 stories on **every** run over a multi-day window while its sibling categories fluctuate normally, treat that as a signal to check the query string itself before assuming it's just a quiet news day or a widening-logic gap.

### 2.7 Non-RSS config entries excluded from category counts
`config.yaml` includes `"Weather Forecast 77316"` as a 16th `categories` entry with `max_stories: 0` and an empty `query`. This is not an RSS-fetch category — it's a label used to position the Weather Forecast section in `category_priority` ordering (see 4.8). **Exclude it from all RSS-category checks (2.0, 2.1, 2.3, 3.1)** — it should never be flagged as a "missing category" or a "0-story category needing widening."

### 2.2a Adaptive day-window widening for 0-story categories (planned feature — not yet implemented)

**Spec:** when a category returns 0 stories at the default lookback window, the pipeline should widen the date window incrementally and re-query, up to a **7-day cap**, until it finds at least 3 stories or exhausts the cap. This does not exist in the pipeline yet — the current run shows all three 0-story categories (Conroe TX News, Montgomery County TX News, Hermes Agent News) with no widening attempt at all.

**Prerequisite (pipeline change):** log an explicit line every time widening fires, e.g.:
```
[fetch_rss] Category 'Conroe TX News' returned 0 stories at 1-day window, widening to 2 days
[fetch_rss] Category 'Conroe TX News' widened to 7 days, still 0 stories — giving up
[fetch_rss] Category 'Montgomery County TX News' widened to 3 days, found 4 stories
```

**Harness checks, once implemented:**
- **FAIL** if a category shows 0 stories in the final rendered output with no log evidence that widening was attempted (means the widening logic isn't firing — a real bug, not a quiet-news day).
- **WARN** if a category widened all the way to the 7-day cap and still landed under 3 stories (legitimate low-news day, but surface it rather than silently accept it).
- **PASS** if a category widened and reached ≥3 stories.

**Until implemented:** treat any current 0-story category as a flagged spec gap in the run report (e.g. `"Known gap: Conroe TX News returned 0 stories, adaptive widening not yet built"`) rather than scoring it as a pipeline bug — it's expected behavior until the feature ships. Once F.-style instrumentation exists, upgrade this from a documentation note to a hard FAIL per the rule above.

---

## Phase 3 — Enrichment & Summarization

This is the highest-risk phase — it's where the misalignment bug and quality issues live.

### 3.1 Per-category count vs. expected max
- Source of truth: `max: N` per category as defined in `config.yaml`, verified against the log's `[DEBUG] Categories being fetched` block (see 2.0 — the two must match, or 2.0 already FAILs the run before this check even runs).
- Compare post-dedup count in log AND rendered count in output against this expected max.
- **WARN** if a category is under its expected max (already flagged per your earlier call — surface it, don't block the run). Note: being *at or under* max is normal/expected (feeds don't always have `max` fresh stories available); this WARN is informational, not a quality signal on its own.
- **FAIL** if the rendered count in the output doesn't match the log's post-dedup count for that category (signals a rendering/data-loss bug between Phase 3 and Phase 4).

### 3.2 Summary availability
- Count occurrences of `[Summary unavailable]` in the rendered output.
- **FAIL the run if any occur.** (Per your call — this overrides the log's self-reported "0 failed," since that count is clearly not catching these.)
- Also cross-check: log's "Summaries done: X OK / Y failed" should equal the story count with a real summary — if log says `0 failed` but output has `[Summary unavailable]` entries, flag this discrepancy explicitly in the report (it means the failure counter itself is broken).

### 3.3 Headline/summary keyword alignment
For every story: extract lowercase significant words (strip stopwords, drop words ≤3 chars, drop punctuation) from the headline and from the summary text.

- Compute shared-word count between the two sets.
- **FAIL (flag for review)** if shared word count = 0 — this is the strongest signal of the off-by-one misalignment bug seen in the 2026-07-26 run (e.g. "Global News at 6 Maritimes" headline paired with a Pedro Sánchez/Spain summary).
- **WARN** if shared word count = 1 (borderline; may be legitimate for terse headlines).
- Threshold is a starting point — flag as tunable once we've run this against a few more days of output and can eyeball false-positive rate.

### 3.4 Tag sanity check
- Every `[[tag]]` used inline in a story should appear in the frontmatter `tags:` list.
- **FAIL** if an inline tag is missing from frontmatter (indicates tag generation and frontmatter aggregation are out of sync).
- **WARN** if a story's tags look topically unrelated to its own headline (e.g. a Netanyahu/Mamdani story tagged `[[weather]] [[environment]]`) — this is a secondary symptom of the same misalignment bug in 3.3 and is worth cross-referencing rather than treating as independent.

### 3.5 Generic/low-content summary detection
- Flag summaries matching boilerplate patterns like: "This highlights...", "This suggests...", "This indicates...", "Further details... are not provided", "This serves as a general roundup" used as the *entire* substance of a summary (i.e., summary contains no proper nouns / no numbers / no specific claim).
- **WARN** per occurrence; **FAIL** the run if more than 10% of summaries in a run match this pattern (signals the summarization prompt/model is degrading toward filler).

### 3.6 Max tags per story
- `config.yaml`'s `tagging_config.max_tags` is `5`.
- Count inline `[[tag]]` entries per story in the rendered output.
- **FAIL** if any story exceeds 5 tags — indicates the tagging scorer's cap isn't being enforced.

### 3.7 Tag conflict pairs
- `config.yaml`'s `tag_conflicts` currently defines one pair that should never co-occur on the same story: `['international', 'local']`. The `['international', 'us-focused']` pair has been removed — those dimensions describe different aspects of a story and can validly co-occur for U.S. coverage of international events.
- For every story, check its tag set against the configured conflict pair.
- **FAIL** if a story has both tags from any conflict pair — indicates the conflict-resolution logic in the tagger isn't being applied.

### 3.6 Phase 3 timing
- Log `Phase 3 completed in Xs`.
- **WARN** if X > 200s (current baseline ~154s for 56 stories, so this gives headroom before flagging).

---

## Phase 4 — Rendered Output Structure

| # | Check | Method | Threshold |
|---|---|---|---|
| 4.1 | Frontmatter completeness | `title`, `date`, `time_generated`, `content_age_window`, `story_count_total`, `categories`, `tags` all present and non-empty | FAIL if any missing |
| 4.2 | `story_count_total` accuracy | Frontmatter value vs. actual count of rendered story entries | FAIL if mismatch |
| 4.3 | `categories` count accuracy | Frontmatter value vs. actual number of `## <Category> (N stories)` headers | FAIL if mismatch |
| 4.4 | Empty categories still render | Category header present even at 0 stories | WARN if header missing entirely for a configured category. Also: a 0-story category is no longer "expected behavior" by default — see 2.2a. Until adaptive widening is implemented, log as a known spec gap; once implemented, a 0-story category with no widening evidence is a FAIL per 2.2a |
| 4.5 | URL well-formedness | Every story link is a valid, non-empty URL | FAIL if any story is missing a URL |
| 4.6 | Publish timestamp present | Every story has an `*Originally published on:*` line with a parseable UTC timestamp | FAIL if missing |
| 4.7 | File written to correct path | Log's `File written to <path>` matches `directories.news_dir` from `config.yaml` for that run (paths are dynamic — Dev and Prod point to different folders, don't hardcode either) | FAIL if the log's actual write path doesn't match the resolved `directories.news_dir` value from `config.yaml` at the time of the run |
| 4.8 | Frontmatter required tag segments present | `config.yaml`'s `runtime.frontmatter_tag_segments` (`["daily-intelligently", "news-summary", "ai-generated"]`) — every entry in this list must appear in the rendered frontmatter `tags:` block | **FAIL** if any segment is missing. **Known live bug:** the 2026-07-26 sample output has `news-summary` and `ai-generated` but is missing `daily-intelligently` entirely — confirm whether the tag itself has a typo in the pipeline (e.g. meant to be `daily-brief`) or whether the frontmatter builder is just dropping it |
| 4.9 | Section order matches `category_priority` | Compare the order of `## <Category> (N stories)` headers in the output against `config.yaml`'s `category_priority` list (excluding the non-RSS `"Weather Forecast 77316"` entry — see 2.7 — which corresponds to the Weather Forecast section always rendering first) | **FAIL** if section order doesn't match `category_priority` exactly |

---

## Cross-Cutting — Live Data Integrity (No Fallback/Mock Data)

**Principle:** every data element in the output — weather, station data, lake levels, RSS stories, article enrichment, summaries — must come from a live call made during that run. Nothing cached, hardcoded, or substituted on failure should ever silently ship in the output.

### Prerequisite (pipeline change — not yet in place)
The pipeline currently has fallback/mock logic in places (per your confirmation), but the log doesn't explicitly say when a fallback path fires. To make this checkable with certainty, the pipeline needs to log a tag at the point of every external call:

```
[fetch_weather] [LIVE] Forecast fetched from api.weather.gov
[fetch_weather] [FALLBACK] Using cached climate normal — API timeout
[fetch_rss] [FALLBACK] Category 'Texas News' — using last-known story list, live fetch failed
```

Until this instrumentation exists, treat **F.1 below as blocked** and rely on **F.2** (indirect detection) as the working check.

### F.1 Explicit fallback flag (once instrumented)
- Grep log for `[FALLBACK]`.
- **FAIL the run** if any fallback marker appears anywhere in the log — no exceptions. A run that used fallback data for even one data point should not be treated as a valid daily brief.

### F.2 Indirect detection (works today, backstop until F.1 is wired up)
Compare against the immediately prior run's log/output for the same data sources:

| Check | Method | Threshold |
|---|---|---|
| Weather values frozen across days | Compare `avg_temp_today`, forecast highs/lows, current monthly rainfall, lake fill % against prior run | WARN if identical to prior run; FAIL if identical across 3+ consecutive runs (climate normal high is the one legitimate exception — it's static by design, don't flag it) |
| Placeholder-looking numeric values | Scan weather/lake fields for suspicious defaults: exactly `0`, `100.0`, `50.0`, `-999`, or a literal `None`/`null` string | WARN per occurrence |
| RSS story set frozen across days | Compare fetched URL sets per category against prior run | WARN if >90% overlap (feed likely not actually refreshing) |
| Fetch phase completing implausibly fast | Phase 1 (weather, normally ~10s with 4 network calls) or Phase 2 (RSS, normally ~1s but across 15 live feed hits) finishing near-instantly | WARN if Phase 1 < 2s — likely a skipped live call |

Once F.1 instrumentation lands, F.2 becomes a secondary sanity net rather than the primary detection method — keep both, since F.2 also catches fallback behavior that isn't properly tagged by mistake.

### F.3 Global FAIL / Unavailable string scan
This is the simplest and most reliable signal available right now — both the log and the rendered output already surface failures as literal `FAIL` or `Unavailable` text.

- Grep the **log file** for `FAIL` (case-insensitive) and count occurrences, with surrounding context line.
- Grep the **rendered output** for `Unavailable` (covers `[Summary unavailable]` and any other field that degrades to this string — e.g. weather fields, story metadata) and count occurrences, with the story/section it appears in.
- **Report both counts explicitly in the run report, every run, regardless of pass/fail status elsewhere.**
- **WARN** on any count > 0.
- **FAIL** if the count for a single field/check type exceeds a repeat threshold (e.g. same field failing 2+ runs in a row) — a one-off is a WARN, a pattern is a FAIL.
- This check should run in addition to, not instead of, the specific checks elsewhere in this doc (3.2, F.1, etc.) — those give you *what kind* of failure; this gives you a fast top-line count so nothing slips through uncategorized.

### F.4 Known bug — Climate Normal High mis-source (elevation vs. temperature)
Confirmed recurring failure mode: the "Climate Normal High for today" field sometimes picks up the station's **elevation** instead of its **temperature**, and separately sometimes silently falls back to a **default value of 95°F**.

- **FAIL** if `Climate Normal High` > 115°F — this is the real-world ceiling for actual air temperature in the 77316 (Montgomery/Conroe) area; anything above it is not weather, it's the elevation field bleeding through. (Note: 115°F is a hard cap for *air* temperature specifically — a "feels like" field, if one is ever added, can legitimately run up to ~120°F and should not be checked against this same threshold.)
- **WARN** if `Climate Normal High` == 95°F exactly — matches the known fallback default; not necessarily wrong, but flag it for a manual look since it may mean the live parse silently failed and the fallback caught it without logging as such.
- Same elevation-vs-temperature mix-up risk should be checked wherever else the pipeline pulls paired numeric fields from the same source page (e.g. if average/current monthly rainfall are scraped from the same climate page as elevation) — worth a quick audit of that scraper function specifically.

---

## Pipeline-Level Gates

| # | Check | Method | Threshold |
|---|---|---|---|
| P.1 | Total runtime | Log `PROCESSING COMPLETE: N stories in Xs` | **WARN if total run exceeds 5 minutes (300s)** |
| P.2 | Total story count sanity | Final rendered `story_count_total` | WARN if < 20 or > 100 (unusually thin or bloated run — worth a look, not necessarily wrong) |
| P.3 | No unhandled errors in log | Grep log for `ERROR`, `Traceback`, `Exception` | FAIL if any present and not explicitly handled/logged as recovered |

---

## Run Report Template

**File location & naming:** write the validation report as its own file, in the same `logs/` folder as the run log, using matching date and version so the two sit side-by-side and are easy to pair up:

```
run_log_2026-07-26_v01.md          ← pipeline log (existing)
validation_log_2026-07-26_v01.md   ← this harness's output (new)
```

**Execution model:** the harness runs automatically as **Phase 6** of the pipeline, immediately after every run — no manual invocation needed anymore. Every fix or code change triggers: full pipeline run → Test_validate_run.py → results written to `validation_log_<date>_<version>.md`. (This superseded the original manual/on-demand model once the checks had stabilized against several real runs.)

Findings from each run should be triaged into `TODOS.md`: FAILs as P0 items, WARNs as P1 items, tagged with their check ID (e.g. `**2.6**`) for traceability back to this spec. Watch for findings that share a root cause (e.g. a `4.3` frontmatter-count mismatch and a `4.4` missing-section-header both stemming from the same empty categories) — merge those into a single TODOS.md item rather than tracking the same fix twice under different check IDs.

Every validation pass should produce a short summary like this:

```
Run: DailyBrief-YYYY-MM-DD_vNN
Status: PASS / WARN / FAIL

FAIL (n):
  - [3.2] 4 stories with [Summary unavailable] (South Dakota AI, Nvidia/Microsoft, SpaceX Barchart, Karpathy #2)
  - [3.3] 1 story with zero headline/summary keyword overlap (World News #2 & #3 appear swapped)
  - [2.6] Hermes Agent News query is "herms agent" in config.yaml — typo, should be "hermes agent"
  - [4.8] Frontmatter missing required tag "daily-intelligently" (has news-summary, ai-generated only)

WARN (n):
  - [2.2a] Conroe TX News: 0/5 stories, no widening attempt in log — known gap (feature not yet built)
  - [2.2a] Montgomery County TX News: 0/5 stories, no widening attempt in log — known gap (feature not yet built)
  - [2.2a] Hermes Agent News: 0/5 stories, no widening attempt in log — known gap (feature not yet built)
  - [3.5] 2 summaries flagged as low-content/generic

Timing: 165.8s total (within 300s gate)
```

---

## Open / Tunable Items (revisit after a few more runs)

- **Immediately fixable, not just a harness gap:** `config.yaml`'s `"Hermes Agent News"` query (`"herms agent"`) and the missing `daily-intelligently` frontmatter tag (4.8) are real bugs sitting in the config/pipeline right now, not calibration items. Worth fixing directly rather than waiting on harness runs to keep re-flagging them.
- **Pipeline dev needed — F.1 LIVE/FALLBACK logging.** No explicit tagging exists yet at external call sites; F.2/F.3/F.4 are the working backstop until this lands.
- **Pipeline dev needed — 2.2a adaptive day-window widening.** Not implemented yet (assume 7-day cap per your call). Until built, 0-story categories are logged as known gaps, not failures — though note 2.6 means Hermes specifically isn't actually a widening-gap case, it's a query typo.
- **3.3 keyword overlap threshold** — currently a blunt "0 shared words = flag" rule. Once we've run this against several days of real output, we should look at the false-positive rate and consider moving to stemmed/fuzzy matching or a small overlap-ratio threshold instead of a raw count.
- **P.1 runtime ceiling** — 300s is a starting guess based on current ~166s baseline; tighten once we see variance across multiple runs.
- Whether `story_count_total` in P.2 should tie back to a per-run expected range from `config.yaml` rather than a fixed 20–100 band.
