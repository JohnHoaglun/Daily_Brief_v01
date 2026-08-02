#!/usr/bin/env python3
"""
Corpus capture module for Daily Brief v1.0.92.

Runs the pipeline through Phases 1-3A (config validation, RSS fetch/dedup,
article extraction), then captures story metadata and the exact
build_context() output for each story — before any LLM calls.

Hardened: PROJECT_ROOT-relative output path, --force overwrite guard,
corpus validation (min stories, context coverage, required fields),
metadata enrichment (categories, category_order, context_stats).

Usage:
    python3 scripts/capture_corpus.py --output tests/fixtures/llm_benchmark_contexts.json
    python3 scripts/capture_corpus.py --output ./corpus.json --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from collections import OrderedDict
from datetime import datetime, timezone
# Ensure the daily_brief package is importable (src/ is at project root, scripts/ is sibling)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

import aiohttp
from daily_brief.config import (
    CONFIG_YAML,
    CATEGORIES,
    USER_AGENT,
    VERSION,
)
from daily_brief.config_validator import validate_config
from daily_brief.pipelines.rss_dedup import fetch_and_dedup
from daily_brief.sources.article import stage_extract_article
from daily_brief.sources.rss import format_pub_date
from daily_brief.llm.summarizer import StoryPipelineState, build_context


def _log(msg: str):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def _resolve_output_path(path: str) -> str:
    """Resolve output path relative to PROJECT_ROOT, not CWD."""
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_ROOT, path)


def _check_force(output_path: str, force: bool) -> None:
    """Refuse to overwrite an existing file unless --force is provided."""
    resolved = _resolve_output_path(output_path)
    if os.path.exists(resolved) and not force:
        _log(f"FATAL: Output file already exists: {resolved}")
        _log(f"Use --force to overwrite, or choose a different output path.")
        sys.exit(1)


def _build_context_stats(stories: list) -> dict:
    """Compute context statistics for corpus metadata."""
    lengths = [len(s.get("context", "") or "") for s in stories]
    non_empty = sum(1 for l in lengths if l > 0)
    return {
        "total": len(stories),
        "non_empty": non_empty,
        "median_length": statistics.median(lengths) if lengths else 0,
    }


def _validate_corpus(corpus: dict, min_stories: int, min_context_pct: float) -> list:
    """Validate captured corpus before writing. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    required_top = ["capture_date", "version", "total_stories", "stories"]
    for key in required_top:
        if key not in corpus:
            errors.append(f"Missing top-level key: {key}")

    if not errors and not isinstance(corpus.get("stories"), list):
        errors.append("'stories' must be a list")
        return errors

    stories = corpus.get("stories", [])

    if not stories:
        errors.append("Corpus is empty — no stories captured")

    if corpus.get("total_stories") is not None and corpus["total_stories"] != len(stories):
        errors.append(f"total_stories ({corpus['total_stories']}) != len(stories) ({len(stories)})")

    if len(stories) < min_stories:
        errors.append(f"Only {len(stories)} stories captured, minimum is {min_stories}")

    required_fields = ["title", "url", "category", "snippet", "pub_date", "context"]
    missing_field = False
    for i, story in enumerate(stories):
        for field in required_fields:
            if not isinstance(story, dict) or story.get(field) is None:
                errors.append(f"Story {i}: missing or None field '{field}'")
                missing_field = True

    # Context coverage
    if stories:
        non_empty = sum(1 for s in stories if isinstance(s, dict) and s.get("context", "").strip())
        pct = non_empty / len(stories)
        if pct < min_context_pct:
            errors.append(f"Context coverage {pct:.1%} ({non_empty}/{len(stories)}) below threshold {min_context_pct:.0%}")

    return errors


async def capture(output_path: str, force: bool = False, min_stories: int = 20, min_context_pct: float = 0.8) -> None:
    # --- Resolve output path relative to PROJECT_ROOT ---
    resolved_path = _resolve_output_path(output_path)
    _check_force(output_path, force)

    # --- Config validation gate ---
    config_ok, config_issues = validate_config(CONFIG_YAML)
    if not config_ok:
        _log(f"FATAL: {len(config_issues)} config validation error(s). Aborting.")
        for ci in config_issues:
            _log(f"CONFIG ERROR: {ci}")
        sys.exit(1)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=100, limit_per_host=30, ttl_dns_cache=300),
        headers={"User-Agent": USER_AGENT},
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:

        _log("[Phase 2] Fetching and deduplicating RSS feeds...")
        deduped, dedup_stats = await fetch_and_dedup(session, CATEGORIES, _log)
        total_before = dedup_stats.get("total_before", 0)
        total_after = dedup_stats.get("total_after", 0)
        _log(f"  RSS results: {total_before} -> {total_after} after dedup")

        # --- Build StoryPipelineState objects ---
        stories: list[StoryPipelineState] = []
        for title, link, snippet, pub_dt, cat in deduped:
            s = StoryPipelineState(title, link, snippet, pub_dt, cat)
            stories.append(s)

        # --- Phase 3A: Async article extraction ---
        _log("[Phase 3A] Fetching full articles (external sources only)...")
        await asyncio.gather(
            *(stage_extract_article(s, session) for s in stories),
            return_exceptions=True,
        )
        _log(f"  Article extraction complete for {len(stories)} stories")

    # --- Build corpus data (no LLM calls) ---
    capture_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cat_counts = OrderedDict()

    story_list: list[dict] = []
    for s in stories:
        ctx = build_context(s)
        cat = s.category
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

        pub_date_str = format_pub_date(s.pub_dt) if s.pub_dt else None

        story_list.append({
            "title": s.title,
            "url": s.link,
            "category": s.category,
            "snippet": s.snippet,
            "pub_date": pub_date_str,
            "context": ctx,
        })

    corpus = {
        "capture_date": capture_ts,
        "version": VERSION,
        "total_stories": len(story_list),
        "stories": story_list,
        "categories": dict(cat_counts),
        "category_order": list(cat_counts.keys()),
        "context_stats": _build_context_stats(story_list),
    }

    # --- Validate corpus before writing ---
    validation_errors = _validate_corpus(corpus, min_stories, min_context_pct)
    if validation_errors:
        _log("FATAL: Corpus validation failed:")
        for err in validation_errors:
            _log(f"  - {err}")
        sys.exit(1)

    # --- Write output ---
    out_dir = os.path.dirname(resolved_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(resolved_path, "w", encoding="utf-8") as f:
        json.dump(corpus, f, indent=2, ensure_ascii=False)

    # --- Print summary ---
    stats = corpus["context_stats"]
    print(f"\nCorpus captured: {len(story_list)} stories -> {resolved_path}")
    print(f"  Capture timestamp: {capture_ts}")
    print(f"  Pipeline version:  {VERSION}")
    print(f"  Story context:     {stats['non_empty']}/{stats['total']} non-empty (median {stats['median_length']:.0f} chars)")
    print(f"  Category breakdown:")
    for cat, count in cat_counts.items():
        print(f"    {cat}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture Daily Brief corpus before LLM summarization.",
    )
    parser.add_argument(
        "--output",
        default="tests/fixtures/llm_benchmark_contexts.json",
        help="Output JSON file path (default: tests/fixtures/llm_benchmark_contexts.json)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output file",
    )
    parser.add_argument(
        "--min-stories",
        type=int,
        default=20,
        help="Minimum story count to accept corpus (default: 20)",
    )
    parser.add_argument(
        "--min-context-pct",
        type=float,
        default=0.8,
        help="Minimum fraction of stories with non-empty context (default: 0.8)",
    )
    args = parser.parse_args()
    asyncio.run(capture(args.output, force=args.force, min_stories=args.min_stories, min_context_pct=args.min_context_pct))


if __name__ == "__main__":
    main()
