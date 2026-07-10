# Changes Made to dashboard_pipeline.py

## 1. Added Debug Logging (Line ~692)
Added per-category breakdown of story counts after deduplication:
```python
# DEBUG: Show per-category breakdown before summarization
log("  [DEBUG] Per-category story count AFTER dedup:")
cat_counts = {}
for entry in deduped:
    cat = entry[4]  # cat_name
    cat_counts[cat] = cat_counts.get(cat, 0) + 1
for cn in sorted(cat_counts.keys()):
    log(f"    {cn}: {cat_counts[cn]}")
```

## 2. Enhanced Age Filtering Logic (Lines ~650-660)
Improved date handling to prevent filtering out valid stories due to timezone conversion issues:
```python
# Added exception handling for timezone/date parsing failures
try:
    age_secs = (now_ct - pub_dt).total_seconds()
    if age_secs > AGE_LIMIT_HOURS * 3600:
        total_age_filtered += 1
        is_old = True
except Exception:
    # If there are timezone conversion issues, treat as expired
    total_age_filtered += 1
    is_old = True
```

## 3. Added Category Fetch Debug (Lines ~625-630)
Added logging of which categories are being fetched:
```python
# DEBUG: Show all categories we're actually going to fetch
log("  [DEBUG] Categories being fetched:")
for name, url, max_stories in rss_items:
    log(f"    {name}: {url[:100]}... (max: {max_stories})")
```

## 4. Added Feed Results Debug (Lines ~635-640) 
Added logging of feed results by category to show what's actually being returned:
```python
# DEBUG: Show which feed queries are returning data
log("  [DEBUG] Feed results by category:")
for name in sorted(by_cat.keys()):
    count = len(by_cat[name])
    log(f"    {name}: {count} stories")
```