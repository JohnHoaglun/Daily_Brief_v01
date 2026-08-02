#!/usr/bin/env python3
"""
Corpus capture module for Daily Brief.

Runs the pipeline through Phases 1-3A (config validation, RSS fetch/dedup,
article extraction), then captures story metadata and the exact
build_context() output for each story — before any LLM calls.

Usage:
    python scripts/capture_corpus.py --output tests/fixtures/llm_benchmark_contexts.json
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
# Ensure the daily_brief package is importable (src/ is at project root, scripts/ is sibling)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

import aiohttp
from collections import OrderedDict
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


async def capture(output_path: str) -> None:
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

    # --- Capture corpus (no LLM calls) ---
    capture_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stories_with_context = 0
    cat_counts = OrderedDict()

    story_list = []
    for s in stories:
        ctx = build_context(s)
        if ctx and ctx.strip():
            stories_with_context += 1
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
    }

    # --- Write output ---
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(corpus, f, indent=2, ensure_ascii=False)

    # --- Print summary ---
    print(f"\nCorpus captured: {len(story_list)} stories -> {output_path}")
    print(f"  Capture timestamp: {capture_ts}")
    print(f"  Pipeline version:  {VERSION}")
    print(f"  Stories with non-empty context: {stories_with_context}/{len(story_list)}")
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
    args = parser.parse_args()
    asyncio.run(capture(args.output))


if __name__ == "__main__":
    main()
