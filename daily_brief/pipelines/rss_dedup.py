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
from zoneinfo import ZoneInfo


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

    # Concurrent fetch — pass None so fetch_feed returns full candidate pool
    all_results = await asyncio.gather(
        *(fetch_feed(session, n, u, None) for n, u, m in rss_items),
        return_exceptions=True,
    )

    # Collect by category — preserve input order
    cat_order: List[Tuple[str, int]] = []
    by_cat: Dict[str, List[Any]] = {}
    for i, result in enumerate(all_results):
        if isinstance(result, Exception):
            cat_order.insert(i, (rss_items[i][0], rss_items[i][2]))
            continue
        name, entries = result
        if not isinstance(entries, list):
            entries = []
        by_cat[name] = entries
        cat_order.append((name, rss_items[i][2]))

    total_before_dedup = sum(len(v) for v in by_cat.values())
    log_fn(f"  Fetched {total_before_dedup} stories from {len(by_cat)} categories")

    log_fn("  [DEBUG] Feed results by category:")
    for name in sorted(by_cat.keys()):
        count = len(by_cat[name])
        log_fn(f"    {name}: {count} stories")

    # Per-category processing: filter, widen locally, then cap to max_stories
    deduped: List[Tuple[str, str, str, Optional[datetime], str]] = []
    total_age_filtered = 0
    total_dup_filtered = 0
    total_cross_dup_filtered = 0
    seen_per_cat: Dict[str, Set[str]] = {}

    for cat_name, max_stories in cat_order:
        age_limit = CATEGORY_AGE_LIMITS.get(cat_name, DEFAULT_AGE_LIMIT_HOURS)
        candidates = by_cat.get(cat_name, [])

        # Filter at the default age limit
        initial: List[Tuple[str, str, str, Optional[datetime], str]] = []
        added, af, df = dedup_entries(
            candidates, now_ct, cat_name, age_limit, seen_per_cat, initial
        )
        total_age_filtered += af
        total_dup_filtered += df

        # If < 3 stories, widen locally using the same candidate pool
        start_count = len(initial)
        if start_count < 3:
            log_fn(
                f"  [WIDEN] '{cat_name}' had {start_count} stories at {age_limit}h — "
                f"attempting local widening (2d-7d)"
            )
            w_af, w_df, w_added = _widen_category_local(
                cat_name, candidates, initial, now_ct, seen_per_cat,
            )
            total_age_filtered += w_af
            total_dup_filtered += w_df
            final_count = len(initial)
            log_fn(
                f"  [WIDEN] '{cat_name}' local widening complete: "
                f"{start_count} -> {final_count} stories (added: {w_added})"
            )
            if w_added > 0:
                log_fn(
                    f"  [WIDEN] '{cat_name}' recovered {w_added} additional stories (total: {final_count})"
                )
            else:
                log_fn(
                    f"  [WIDEN] '{cat_name}' exhausted to 7d: still at {start_count} stories"
                )

        # Cap to max_stories output
        cap = max_stories if max_stories > 0 else 9999
        if len(initial) > cap:
            initial = initial[:cap]

        deduped.extend(initial)

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


def _widen_category_local(
    cat_name: str,
    candidates: List[Tuple[str, str, str, Optional[datetime]]],
    accepted: List[Tuple[str, str, str, Optional[datetime], str]],
    now_ct: datetime,
    seen_map: Dict[str, Set[str]],
) -> Tuple[int, int, int]:
    """Locally widen a category by examining already-fetched candidates at wider age windows.

    Iterates 2d-7d age windows. For each window, only entries that are newly eligible
    (older than the previous cutoff but within the new one) are re-examined. Entries
    that pass dedup, obituary, and real-estate filters are appended to *accepted*.

    Args:
        cat_name: category name
        candidates: full candidate list (already sorted newest-first by fetch_feed)
        accepted: mutable list of accepted entries, mutated in place
        now_ct: current datetime in timezone
        seen_map: dict of cat_name → set of normalized titles (mutated in place)

    Returns:
        (age_filtered, dup_filtered, recovered_count)
    """
    from daily_brief.sources.rss import normalize_title
    from daily_brief.utils import is_obituary_title, is_realt_estate_title

    age_filtered = 0
    dup_filtered = 0
    recovered = 0
    prev_hours = 24.0

    seen = seen_map.setdefault(cat_name, set())

    for widen_days in range(2, 8):
        widen_hours = widen_days * 24

        for title, link, snippet, pub_dt in candidates:
            # Only look at entries not yet eligible at the previous cutoff
            if pub_dt is not None:
                try:
                    age_secs = (now_ct - pub_dt).total_seconds()
                    age_hrs = age_secs / 3600
                except Exception:
                    age_hrs = None

                if age_hrs is not None:
                    # Already within the previous window — was already processed
                    if age_hrs <= prev_hours:
                        continue
                    # Outside this window — skip, may be eligible later or not at all
                    if age_hrs > widen_hours:
                        continue
                    # Within this widening band — eligible
                    # (don't count as age_filtered since it was already counted)
                else:
                    # Undated — already processed in initial pass
                    continue
            else:
                # Undated — already processed in initial pass
                continue

            norm = normalize_title(title)
            if norm in seen:
                dup_filtered += 1
                continue
            if is_realt_estate_title(title) or is_obituary_title(title):
                continue
            seen.add(norm)
            accepted.append((title, link, snippet, pub_dt, cat_name))
            recovered += 1

        prev_hours = widen_hours
        if len(accepted) >= 3:
            break

    return age_filtered, dup_filtered, recovered
