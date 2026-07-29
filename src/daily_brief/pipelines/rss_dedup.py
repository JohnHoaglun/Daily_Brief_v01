"""
Daily Brief RSS Dedup Pipeline
===============================
Extracted Phase 2 logic: RSS feed fetching, per-category deduplication,
adaptive widening, and cross-category deduplication.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


async def fetch_and_dedup(
    session: Any,
    categories: List[Tuple[str, str, int]],
    log_fn: Callable[[str], None],
) -> Tuple[List[Tuple[str, str, str, Optional[datetime], str]], Dict[str, int]]:
    """Fetch all RSS feeds, dedup per-category, widen underpopulated, cross-cat dedup.

    Args:
        session: aiohttp.ClientSession
        categories: list of (name, query, max_stories) from CATEGORIES
        log_fn: logging callback

    Returns:
        (deduped, stats) where:
            deduped: list of (title, link, snippet, pub_dt, category) tuples
            stats: dict with counts
    """
    from daily_brief.config import CATEGORY_AGE_LIMITS, DEFAULT_AGE_LIMIT_HOURS, TIMEZONE as CFG_TIMEZONE
    from daily_brief.sources.rss import build_rss_url, fetch_feed, normalize_title
    try:
        active_tz = ZoneInfo(CFG_TIMEZONE)
    except Exception:
        from datetime import timezone as tz
        active_tz = tz.utc

    now_ct = datetime.now(active_tz)

    rss_items = [(c[0], build_rss_url(c[1]), c[2]) for c in categories if c[1]]
    log_fn(f"\n[Phase 2] Fetching {len(rss_items)} RSS feeds...")

    log_fn("  [DEBUG] Categories being fetched:")
    for name, url, max_stories in rss_items:
        log_fn(f"    {name}: {url[:100]}... (max: {max_stories})")

    # Concurrent fetch
    all_results = await asyncio.gather(
        *(fetch_feed(session, n, u, m) for n, u, m in rss_items),
        return_exceptions=True,
    )

    # Collect by category
    by_cat: Dict[str, List[Any]] = {}
    for result in all_results:
        if isinstance(result, Exception):
            continue
        name, entries = result
        if not isinstance(entries, list):
            entries = []
        by_cat[name] = entries

    total_before_dedup = sum(len(v) for v in by_cat.values())
    log_fn(f"  Fetched {total_before_dedup} stories from {len(by_cat)} categories")

    log_fn("  [DEBUG] Feed results by category:")
    for name in sorted(by_cat.keys()):
        count = len(by_cat[name])
        log_fn(f"    {name}: {count} stories")

    # Per-category dedup
    deduped: List[Tuple[str, str, str, Optional[datetime], str]] = []
    total_age_filtered = 0
    total_dup_filtered = 0
    total_cross_dup_filtered = 0
    seen_per_cat: Dict[str, Set[str]] = {}
    cats_with_zero_stories: List[Tuple[str, int]] = []

    for cat_name in by_cat:
        age_limit = CATEGORY_AGE_LIMITS.get(cat_name, DEFAULT_AGE_LIMIT_HOURS)
        added, af, df = dedup_entries(
            by_cat[cat_name], now_ct, cat_name, age_limit, seen_per_cat, deduped
        )
        total_age_filtered += af
        total_dup_filtered += df
        if added < 3:
            cats_with_zero_stories.append((cat_name, added))

    # Adaptive widening
    for cat_name, existing_count in cats_with_zero_stories:
        final_count, added_count, widen_af, widen_df = await widen_category(
            session, cat_name, existing_count, seen_per_cat, deduped, now_ct, categories, log_fn
        )
        total_age_filtered += widen_af
        total_dup_filtered += widen_df

    # Cross-category dedup
    global_seen: Set[str] = set()
    cross_deduped: List[Tuple[str, str, str, Optional[datetime], str]] = []
    for entry in deduped:
        title, link, snippet, pub_dt, cat_name = entry
        norm = normalize_title(title)
        if norm in global_seen:
            total_cross_dup_filtered += 1
            continue
        global_seen.add(norm)
        cross_deduped.append(entry)
    deduped = cross_deduped

    total_after_dedup = len(deduped)
    log_fn(
        f"  Deduplicated: {total_before_dedup} -> {total_after_dedup} stories "
        f"(age-filtered: {total_age_filtered}, dup-filtered: {total_dup_filtered}, cross-cat-filtered: {total_cross_dup_filtered})"
    )

    # Per-category debug count
    log_fn("  [DEBUG] Per-category story count AFTER dedup:")
    cat_counts: Dict[str, int] = {}
    for entry in deduped:
        cat = entry[4]
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    for cn in sorted(cat_counts.keys()):
        log_fn(f"    {cn}: {cat_counts[cn]}")

    stats: Dict[str, int] = {
        "total_before": total_before_dedup,
        "total_after": total_after_dedup,
        "age_filtered": total_age_filtered,
        "dup_filtered": total_dup_filtered,
        "cross_dup_filtered": total_cross_dup_filtered,
    }

    return deduped, stats


def dedup_entries(
    entries: List[Tuple[str, str, str, Optional[datetime]]],
    now_ct: datetime,
    cat_name: str,
    age_limit_hours: float,
    seen_map: Dict[str, Set[str]],
    deduped_list: List[Tuple[str, str, str, Optional[datetime], str]],
) -> Tuple[int, int, int]:
    """Dedup and age-filter a single category's entries.

    Appends valid (title, link, snippet, pub_dt, category) tuples to deduped_list.

    Args:
        entries: list of (title, link, snippet, pub_dt) tuples
        now_ct: current datetime in timezone
        cat_name: category name
        age_limit_hours: max age in hours
        seen_map: dict of cat_name → set of normalized titles (mutated in place)
        deduped_list: list that valid entries are appended to

    Returns:
        (added, age_filtered, dup_filtered) — counts only
    """
    from daily_brief.sources.rss import normalize_title
    from daily_brief.utils import is_obituary_title, is_realt_estate_title

    added = age_filtered = dup_filtered = 0
    for title, link, snippet, pub_dt in entries:
        is_old = False
        if pub_dt is not None:
            try:
                age_secs = (now_ct - pub_dt).total_seconds()
                if age_secs > age_limit_hours * 3600:
                    age_filtered += 1
                    is_old = True
            except Exception:
                age_filtered += 1
                is_old = True
        if is_old:
            continue
        norm = normalize_title(title)
        if norm in seen_map.get(cat_name, set()):
            dup_filtered += 1
            continue
        seen_map.setdefault(cat_name, set()).add(norm)
        if is_realt_estate_title(title) or is_obituary_title(title):
            continue
        deduped_list.append((title, link, snippet, pub_dt, cat_name))
        added += 1
    return added, age_filtered, dup_filtered


async def widen_category(
    session: Any,
    cat_name: str,
    existing_count: int,
    seen_map: Dict[str, Set[str]],
    deduped_list: List[Tuple[str, str, str, Optional[datetime], str]],
    now_ct: datetime,
    categories: List[Tuple[str, str, int]],
    log_fn: Callable[[str], None],
) -> Tuple[int, int, int, int]:
    """Adaptive widening: re-fetch with 2d-7d age window until >=3 stories.

    Args:
        session: aiohttp.ClientSession
        cat_name: category name
        existing_count: stories already in deduped_list for this category
        seen_map: dict of cat_name → set of normalized titles (mutated in place)
        deduped_list: list that valid entries are appended to
        now_ct: current datetime in timezone
        categories: list of (name, query, max_stories) from CATEGORIES
        log_fn: logging callback

    Returns:
        (final_count, added_count, age_filtered, dup_filtered)
    """
    from daily_brief.config import CATEGORY_AGE_LIMITS, DEFAULT_AGE_LIMIT_HOURS
    from daily_brief.sources.rss import build_rss_url, fetch_feed

    matching_cat = next((c for c in categories if c[0] == cat_name), None)
    if not matching_cat or not matching_cat[1]:
        return existing_count, 0, 0, 0
    query = matching_cat[1]
    max_stories = matching_cat[2]
    default_limit = CATEGORY_AGE_LIMITS.get(cat_name, DEFAULT_AGE_LIMIT_HOURS)

    cat_widened_count = existing_count
    last_wide_days = 0
    widen_af = 0
    widen_df = 0
    log_fn(
        f"  [WIDEN] '{cat_name}' had {existing_count} stories at {default_limit}h — attempting widening (2d-7d)"
    )
    for widen_days in range(2, 8):
        widen_hours = widen_days * 24
        rss_url = build_rss_url(query)
        result = await fetch_feed(session, cat_name, rss_url, max_stories)
        name, entries = result
        if not entries:
            log_fn(f"    [{widen_days}d] no entries from feed")
            continue
        added, af, df = dedup_entries(
            entries, now_ct, name, widen_hours, seen_map, deduped_list
        )
        widen_af += af
        widen_df += df
        if added > 0:
            cat_widened_count += added
            last_wide_days = widen_days
            log_fn(
                f"    [{widen_days}d] +{added} stories (cumulative: {cat_widened_count})"
            )
        else:
            log_fn(f"    [{widen_days}d] 0 added")
        if cat_widened_count >= 3:
            break
    log_fn(
        f"  [WIDEN] '{cat_name}' widening complete: {existing_count} -> {cat_widened_count} stories (added: {cat_widened_count - existing_count})"
    )
    if cat_widened_count > existing_count:
        log_fn(
            f"  [WIDEN] '{cat_name}' recovered {cat_widened_count - existing_count} additional stories (total: {cat_widened_count}, last successful: {last_wide_days}d)"
        )
    else:
        log_fn(
            f"  [WIDEN] '{cat_name}' exhausted to 7d: still at {existing_count} stories"
        )
    return cat_widened_count, cat_widened_count - existing_count, widen_af, widen_df
