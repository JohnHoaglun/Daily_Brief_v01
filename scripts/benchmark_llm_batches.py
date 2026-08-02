#!/usr/bin/env python3
"""Benchmark LLM batch summarization: batch_size x concurrency matrix.

Usage:
    python3 scripts/benchmark_llm_batches.py [--fixture PATH] [--batch-sizes 3 4 5 6] \
        [--concurrencies 1 2] [--warmups 1] [--runs 3] [--host URL] [--model NAME] \
        [--output PATH]
"""

import argparse
import asyncio
import json
import os
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
SRC_DIR = PROJECT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from daily_brief.config import LLM_MODEL as CFG_MODEL, OLLAMA_HOST as CFG_HOST, VERSION
from daily_brief.llm.client import create_llm_client
from daily_brief.llm.summarizer import (
    StoryPipelineState,
    batch_summarize_all,
    SYSTEM_BATCH_PROMPT,
)


# ---------------------------------------------------------------------------
# Instrumentation
# ---------------------------------------------------------------------------
class _ConcurrencyTracker:
    """Thread-safe concurrency tracker for instrumented LLM calls."""

    def __init__(self):
        self.active = 0
        self.max_observed = 0
        self.batch_calls = 0
        self.single_calls = 0
        self.wall_start = time.monotonic()

    def reset(self):
        self.active = 0
        self.max_observed = 0
        self.batch_calls = 0
        self.single_calls = 0
        self.wall_start = time.monotonic()

    @property
    def elapsed_s(self):
        return time.monotonic() - self.wall_start


class InstrumentedClient:
    """Wraps an LLMClient, instrumenting chat_completions_create with call-timing/concurrency."""

    def __init__(self, client, tracker: _ConcurrencyTracker):
        self._orig = client.chat_completions_create
        self._client = client
        self._tracker = tracker
        client.chat_completions_create = self._call

    async def _call(self, **kwargs):
        messages = kwargs.get("messages", [])
        sys_prompt = ""
        for msg in messages:
            if msg.get("role") == "system":
                sys_prompt = msg.get("content", "")
                break

        is_batch = bool(SYSTEM_BATCH_PROMPT and sys_prompt.startswith(SYSTEM_BATCH_PROMPT[:60])) or \
                   bool(SYSTEM_BATCH_PROMPT and sys_prompt == SYSTEM_BATCH_PROMPT)

        self._tracker.active += 1
        if self._tracker.active > self._tracker.max_observed:
            self._tracker.max_observed = self._tracker.active
        if is_batch:
            self._tracker.batch_calls += 1
        else:
            self._tracker.single_calls += 1

        try:
            return await self._orig(**kwargs)
        finally:
            self._tracker.active -= 1

    def detach(self):
        self._client.chat_completions_create = self._orig


# ---------------------------------------------------------------------------
# Standalone validators (mirror summarizer.py logic without re-importing)
# ---------------------------------------------------------------------------
def _is_refusal(text):
    if not text:
        return False
    t = text.strip().lower()
    return any(p in t for p in [
        "please provide the article", "i don't have access", "i do not have access",
        "i can't", "i cannot", "cannot summarize", "no article content",
        "unable to summarize", "article not provided", "no content available",
        "write a detailed summary for you", "i am not able to", "i'm not able to",
        "please provide the source",
    ])


def _is_boilerplate(text):
    if not text:
        return False
    t = text.strip().lower()
    return any(p in t for p in [
        "this highlights a significant", "this suggests a", "this indicates a",
        "further details on the nature", "further details are not", "are not included",
        "are not specified", "details regarding", "this serves as", "this demonstrates",
        "this underscores", "this reflects", "this signals", "this article discusses",
        "this story covers", "the author writes", "according to", "the report states",
        "in this piece", "this piece explores", "this article explores",
        "the article examines", "this story examines", "the following article",
        "the following story",
    ])


def _count_sentences(text):
    if not text:
        return 0
    return len([p for p in re.split(
        r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", re.sub(r"\s+", " ", str(text)).strip()
    ) if p.strip()])


def _is_valid_summary(summary, headline):
    if not summary or not summary.strip():
        return False
    if _is_boilerplate(summary):
        return False
    normalized = re.sub(r"\s+", " ", summary).strip().lower()
    headline_norm = re.sub(r"\s+", " ", headline).strip().lower()
    if normalized == headline_norm or normalized.startswith(headline_norm + "."):
        return False
    if _count_sentences(summary) < 2:
        return False
    return True


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------
def load_corpus(fixture_path):
    """Load JSON corpus and reconstruct StoryPipelineState objects.

    Expected fixture format (dict or list of dicts):
    { "stories": [{title, url, category, snippet, pub_date, context}, ...] }
    or just [{title, url, category, snippet, pub_date, context}, ...]
    """
    with open(fixture_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if isinstance(data, dict):
        stories_data = data.get("stories", data.get("corpus", []))
    elif isinstance(data, list):
        stories_data = data
    else:
        stories_data = []

    stories = []
    for item in stories_data:
        if not isinstance(item, dict):
            continue
        story = StoryPipelineState(
            title=item.get("title", ""),
            link=item.get("url", item.get("link", "")),
            snippet=item.get("snippet", ""),
            pub_dt=item.get("pub_date", item.get("pub_dt", "")),
            category=item.get("category", "Uncategorized"),
        )
        story.context = item.get("context", "")
        stories.append(story)

    return stories


def clone_stories(stories):
    """Return fresh StoryPipelineState copies with summary reset."""
    clones = []
    for s in stories:
        ns = StoryPipelineState(
            title=s.title, link=s.link, snippet=s.snippet,
            pub_dt=s.pub_dt, category=s.category,
        )
        ns.context = s.context
        ns.summary = None
        clones.append(ns)
    return clones


def corpus_metadata(stories):
    cats = defaultdict(int)
    for s in stories:
        cats[s.category] += 1
    return {"total_stories": len(stories), "categories": dict(cats)}


# ---------------------------------------------------------------------------
# Cell execution
# ---------------------------------------------------------------------------
def classify_summaries(stories):
    """Count summary quality categories across a list of stories."""
    valid = 0
    invalid_batch = 0
    boilerplate = 0
    refusal = 0
    auto_fallback = 0
    unavailable = 0

    for s in stories:
        sm = s.summary or ""
        if not sm.strip():
            invalid_batch += 1
        elif sm.startswith("[Auto]"):
            auto_fallback += 1
        elif sm.startswith("[Summary"):
            unavailable += 1
        elif _is_boilerplate(sm):
            boilerplate += 1
        elif _is_refusal(sm):
            refusal += 1
        else:
            valid += 1

    return {
        "valid_summaries": valid,
        "invalid_batch": invalid_batch,
        "boilerplate": boilerplate,
        "refusal": refusal,
        "auto_fallback": auto_fallback,
        "unavailable": unavailable,
    }


async def run_single(stories, batch_size, concurrency, client):
    """Execute one benchmark run for a given cell. Returns (wall_time, result)."""
    tracker = _ConcurrencyTracker()
    instrumented = InstrumentedClient(client, tracker)
    clones = clone_stories(stories)

    wall_start = time.monotonic()
    await batch_summarize_all(
        client, clones,
        batch_size=batch_size, max_concurrency=concurrency,
    )
    wall_time = time.monotonic() - wall_start
    instrumented.detach()

    counts = classify_summaries(clones)
    total = len(clones)
    sps = round(total / wall_time, 2) if wall_time > 0 else 0.0

    return {
        "wall_time_s": round(wall_time, 3),
        "batch_calls": tracker.batch_calls,
        "fallback_calls": tracker.single_calls,
        "max_concurrency_observed": tracker.max_observed,
        **counts,
        "stories_per_second": sps,
        "sub_batch_count": tracker.batch_calls,
    }


# ---------------------------------------------------------------------------
# Table output
# ---------------------------------------------------------------------------
def format_table(cells):
    header = f"{'BS':>3} {'MC':>3}  {'Median(s)':>10} {'Min(s)':>9} {'Max(s)':>9}  " \
             f"{'Valid':>5} {'Batch':>5} {'Fallb':>5} {'MaxC':>4} {'SpS':>6}"
    sep = "-" * len(header)
    lines = [header, sep]

    for cell in sorted(cells, key=lambda c: (c["settings"]["batch_size"], c["settings"]["max_concurrency"])):
        s = cell["settings"]
        wall_times = [r["wall_time_s"] for r in cell["runs"]]
        valids = [r["valid_summaries"] for r in cell["runs"]]
        bs = [r["batch_calls"] for r in cell["runs"]]
        fs = [r["fallback_calls"] for r in cell["runs"]]
        mc = [r["max_concurrency_observed"] for r in cell["runs"]]
        sps = [r["stories_per_second"] for r in cell["runs"]]

        row = f"{s['batch_size']:>3} {s['max_concurrency']:>3}  " \
              f"{cell['median_wall_time_s']:>10.3f} {cell['min_wall_time_s']:>9.3f} {cell['max_wall_time_s']:>9.3f}  " \
              f"{int(statistics.median(valids)):>5} {int(statistics.median(bs)):>5} " \
              f"{int(statistics.median(fs)):>5} {int(statistics.median(mc)):>4} " \
              f"{round(statistics.median(sps), 2):>6.2f}"
        lines.append(row)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main benchmark driver
# ---------------------------------------------------------------------------
async def main_async(args):
    host = args.host
    model = args.model
    fixture_path = args.fixture
    output_path = args.output
    batch_sizes = args.batch_sizes
    concurrencies = args.concurrencies
    warmups = args.warmups
    runs = args.runs

    stories = load_corpus(fixture_path)
    cmeta = corpus_metadata(stories)
    total = cmeta["total_stories"]

    print(f"Corpus: {total} stories across {len(cmeta['categories'])} categories")
    print(f"Model: {model} @ {host}")

    matrix = [(bs, mc) for bs in batch_sizes for mc in concurrencies]
    n_cells = len(matrix)
    print(f"Matrix: {len(batch_sizes)} batch-sizes x {len(concurrencies)} concurrencies = {n_cells} cells")
    print(f"Warmups: {warmups}, Runs: {runs} (total executions: {n_cells * (warmups + runs)})")
    print()

    client = create_llm_client(model=model, base_url=host)

    cell_results = defaultdict(list)

    # --- Warmup runs (fixed order, unrecorded) ---
    print("Warmup runs...")
    for bs, mc in matrix:
        clones = clone_stories(stories)
        await batch_summarize_all(
            client, clones, batch_size=bs, max_concurrency=mc,
        )
        status = f"  [{bs},{mc}] done"
        print(f"\r{status}", end="", flush=True)
    print("\r" + " " * 40, end="\r")
    print("Warmup complete.")
    print()

    # --- Recorded runs (rotated order per repetition) ---
    print("Benchmark runs...")
    sys.stdout.flush()

    for rep in range(1, runs + 1):
        rng = random.Random(rep * 42)
        order = list(matrix)
        rng.shuffle(order)

        for exec_idx, (bs, mc) in enumerate(order):
            result = await run_single(stories, bs, mc, client)
            cell_results[(bs, mc)].append(result)

            progress = f"Rep {rep}/{runs} | {bs},{mc} | {result['wall_time_s']:.1f}s | " \
                       f"{result['valid_summaries']}/{total} valid | " \
                       f"{result['batch_calls']}batch/{result['fallback_calls']}fallback"
            sys.stdout.write(f"\r\033[K{progress}  [{exec_idx+1}/{len(order)}]   ")
            sys.stdout.flush()

    sys.stdout.write("\r" + " " * 120 + "\r")
    print("Benchmark complete.")
    print()

    # --- Aggregate per cell ---
    output_cells = []
    for bs in batch_sizes:
        for mc in concurrencies:
            recs = cell_results.get((bs, mc), [])
            if not recs:
                continue

            # Add run numbers
            for i, r in enumerate(recs):
                r["run"] = i + 1

            wall_times = [r["wall_time_s"] for r in recs]
            cell = {
                "settings": {"batch_size": bs, "max_concurrency": mc},
                "runs": recs,
                "median_wall_time_s": round(statistics.median(wall_times), 3),
                "min_wall_time_s": round(min(wall_times), 3),
                "max_wall_time_s": round(max(wall_times), 3),
            }
            output_cells.append(cell)

    # --- Determine baseline and winner ---
    baseline_cell = None
    for cell in output_cells:
        if cell["settings"]["batch_size"] == 3 and cell["settings"]["max_concurrency"] == 1:
            baseline_cell = cell
            break

    baseline = None
    winner = None

    if baseline_cell:
        baseline = {
            "settings": dict(baseline_cell["settings"]),
            "median_wall_time_s": baseline_cell["median_wall_time_s"],
        }

        baseline_valid = int(statistics.median([r["valid_summaries"] for r in baseline_cell["runs"]]))
        baseline_median = baseline_cell["median_wall_time_s"]

        best = None
        best_med = float("inf")

        for cell in output_cells:
            if cell is baseline_cell:
                continue
            med = cell["median_wall_time_s"]
            cell_valid = int(statistics.median([r["valid_summaries"] for r in cell["runs"]]))
            if med < best_med and med < baseline_median and cell_valid >= baseline_valid * 0.95:
                best = cell
                best_med = med

        if best and best_med < baseline_median:
            improvement = (baseline_median - best_med) / baseline_median
            if improvement >= 0.10:
                winner = {
                    "settings": dict(best["settings"]),
                    "median_wall_time_s": best["median_wall_time_s"],
                    "improvement_pct": round(improvement * 100, 1),
                }

    # --- Write output ---
    output = {
        "benchmark_date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "version": VERSION,
        "config": {
            "model": model,
            "host": host,
            "fixture_path": os.path.abspath(fixture_path),
        },
        "corpus_metadata": cmeta,
        "cells": output_cells,
        "baseline": baseline,
        "winner": winner,
    }

    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    # --- Print table ---
    print("=" * 50)
    print("  LLM Batch Benchmark Results")
    print("=" * 50)
    print()
    print(format_table(output_cells))
    print()

    if baseline:
        print(f"Baseline (3, 1): {baseline['median_wall_time_s']:.3f}s median")
    if winner:
        print(f"WINNER: bs={winner['settings']['batch_size']}, mc={winner['settings']['max_concurrency']}  "
              f"({winner['median_wall_time_s']:.3f}s, {winner['improvement_pct']:.1f}% faster)")
    elif baseline:
        print("No winner — no cell improved >= 10% over baseline without quality regression (95% valid threshold)")
    print()
    print(f"Full JSON: {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Benchmark LLM batch summarization")
    p.add_argument("--fixture", default=str(PROJECT_DIR / "tests" / "fixtures" / "llm_benchmark_contexts.json"),
                    help="JSON corpus fixture path")
    p.add_argument("--batch-sizes", type=int, nargs="+", default=[3, 4, 5, 6],
                    help="Batch sizes to test (space-separated)")
    p.add_argument("--concurrencies", type=int, nargs="+", default=[1, 2],
                    help="Concurrency values to test (space-separated)")
    p.add_argument("--warmups", type=int, default=1,
                    help="Unrecorded warmup runs per cell")
    p.add_argument("--runs", type=int, default=3,
                    help="Recorded runs per cell")
    p.add_argument("--host", default=CFG_HOST,
                    help=f"vLLM endpoint (default: {CFG_HOST})")
    p.add_argument("--model", default=CFG_MODEL,
                    help=f"Model name (default: {CFG_MODEL})")
    p.add_argument("--output", default=str(PROJECT_DIR / "reports" / "llm_batch_benchmark.json"),
                    help="JSON output file path")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
