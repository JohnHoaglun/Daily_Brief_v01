#!/usr/bin/env python3
"""Benchmark LLM batch summarization: batch_size x concurrency matrix.

Usage:
    python3 -m daily_brief.benchmark_llm_batches [--fixture PATH] [--batch-sizes 3 4 5 6] \
        [--concurrencies 1 2] [--warmups 1] [--runs 3] [--host URL] [--model NAME] \
        [--output PATH]
"""

import argparse
import asyncio
import hashlib
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

from daily_brief.config import LLM_MODEL as CFG_MODEL, OLLAMA_HOST as CFG_HOST, LOG_DIR, VERSION
from daily_brief.llm.client import create_llm_client
from daily_brief.llm.summarizer import (
    StoryPipelineState,
    batch_summarize_all,
    SYSTEM_BATCH_PROMPT,
    _is_valid_summary,
    _is_boilerplate,
    _is_refusal,
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
        self.latencies = []
        self.exceptions = 0
        self.sub_batch_sizes = []

    def reset(self):
        self.active = 0
        self.max_observed = 0
        self.batch_calls = 0
        self.single_calls = 0
        self.wall_start = time.monotonic()
        self.latencies = []
        self.exceptions = 0
        self.sub_batch_sizes = []

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

        call_start = time.monotonic()
        try:
            result = await self._orig(**kwargs)
            elapsed = time.monotonic() - call_start
            self._tracker.latencies.append(elapsed)
            if is_batch:
                user_msg = ""
                for msg in messages:
                    if msg.get("role") == "user":
                        user_msg = msg.get("content", "")
                        break
                separators = user_msg.count("\n---\n\n")
                self._tracker.sub_batch_sizes.append(separators + 1)
            return result
        except Exception:
            self._tracker.exceptions += 1
            raise
        finally:
            self._tracker.active -= 1

    def detach(self):
        self._client.chat_completions_create = self._orig


# ---------------------------------------------------------------------------
# Matrix validation
# ---------------------------------------------------------------------------
def _validate_matrix(batch_sizes, concurrencies):
    """Validate and deduplicate the benchmark matrix. Exits on invalid input."""
    bs = sorted(set(batch_sizes))
    mc = sorted(set(concurrencies))

    if any(b <= 0 for b in bs):
        print(f"Error: batch_size must be > 0, got {bs}", file=sys.stderr)
        sys.exit(1)
    if any(m <= 0 for m in mc):
        print(f"Error: max_concurrency must be > 0, got {mc}", file=sys.stderr)
        sys.exit(1)
    if 3 not in bs or 1 not in mc:
        print("Error: baseline cell (batch_size=3, max_concurrency=1) must be in the matrix", file=sys.stderr)
        sys.exit(1)

    return bs, mc



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
    auto_fallback = 0
    unavailable = 0
    boilerplate = 0
    refusal = 0
    invalid = 0

    for s in stories:
        sm = s.summary or ""
        if sm.startswith("[Auto]"):
            auto_fallback += 1
        elif sm.startswith("[Summary"):
            unavailable += 1
        elif not sm.strip():
            invalid += 1
        elif _is_refusal(sm):
            refusal += 1
        elif _is_boilerplate(sm):
            boilerplate += 1
        elif _is_valid_summary(sm, s.title):
            valid += 1
        else:
            invalid += 1

    total = len(stories)
    return {
        "valid_summaries": valid,
        "auto_fallback": auto_fallback,
        "unavailable": unavailable,
        "boilerplate": boilerplate,
        "refusal": refusal,
        "invalid": invalid,
        "total": total,
        "valid_rate": valid / total if total else 0,
        "auto_fallback_rate": auto_fallback / total if total else 0,
        "invalid_rate": invalid / total if total else 0,
        "boilerplate_rate": boilerplate / total if total else 0,
        "refusal_rate": refusal / total if total else 0,
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

    latencies = tracker.latencies
    if latencies:
        sorted_lat = sorted(latencies)
        n = len(sorted_lat)
        p50 = sorted_lat[n // 2]
        idx_95 = min(int(n * 0.95), n - 1)
        p95 = sorted_lat[idx_95]
        lat_max = max(sorted_lat)
    else:
        p50 = 0.0
        p95 = 0.0
        lat_max = 0.0

    return {
        "wall_time_s": round(wall_time, 3),
        "batch_calls": tracker.batch_calls,
        "fallback_calls": tracker.single_calls,
        "max_concurrency_observed": tracker.max_observed,
        **counts,
        "stories_per_second": sps,
        "sub_batch_count": tracker.batch_calls,
        "latency_p50": round(p50, 4),
        "latency_p95": round(p95, 4),
        "latency_max": round(lat_max, 4),
        "exception_count": tracker.exceptions,
        "sub_batch_sizes": tracker.sub_batch_sizes,
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
# Winner selection with quality gates
# ---------------------------------------------------------------------------
def select_winner(output_cells):
    baseline_cell = None
    for cell in output_cells:
        if cell["settings"]["batch_size"] == 3 and cell["settings"]["max_concurrency"] == 1:
            baseline_cell = cell
            break

    if not baseline_cell or not baseline_cell["runs"]:
        return None, None

    baseline_med = baseline_cell["median_wall_time_s"]
    baseline_runs = baseline_cell["runs"]
    baseline_valid_med = int(statistics.median([r["valid_summaries"] for r in baseline_runs]))
    baseline_invalid_rate = float(statistics.median([r.get("invalid_rate", 0) for r in baseline_runs]))
    baseline_auto_rate = float(statistics.median([r.get("auto_fallback_rate", 0) for r in baseline_runs]))
    baseline_bp_refusal_rate = float(statistics.median([
        r.get("boilerplate_rate", 0) + r.get("refusal_rate", 0) for r in baseline_runs
    ]))
    baseline_exceptions = int(statistics.median([r.get("exception_count", 0) for r in baseline_runs]))

    baseline = {
        "settings": dict(baseline_cell["settings"]),
        "median_wall_time_s": baseline_med,
        "valid_summaries": baseline_valid_med,
        "quality": {
            "invalid_rate": baseline_invalid_rate,
            "auto_fallback_rate": baseline_auto_rate,
            "boilerplate_refusal_rate": baseline_bp_refusal_rate,
            "exceptions": baseline_exceptions,
        }
    }

    best = None
    best_med = float("inf")

    for cell in output_cells:
        if cell is baseline_cell:
            continue
        med = cell["median_wall_time_s"]
        if med >= best_med:
            continue
        run = cell["runs"][0] if cell["runs"] else {}
        cand_invalid_rate = float(statistics.median([r.get("invalid_rate", 0) for r in cell["runs"]]))
        cand_auto_rate = float(statistics.median([r.get("auto_fallback_rate", 0) for r in cell["runs"]]))
        cand_bp_refusal_rate = float(statistics.median([
            r.get("boilerplate_rate", 0) + r.get("refusal_rate", 0) for r in cell["runs"]
        ]))
        cand_exceptions = int(statistics.median([r.get("exception_count", 0) for r in cell["runs"]]))

        gates = {}
        speed_ok = med <= baseline_med * 0.90
        gates["speed_improvement"] = {"pass": speed_ok,
            "baseline": baseline_med, "candidate": med,
            "improvement_pct": round((baseline_med - med) / baseline_med * 100, 1)}

        inv_ok = cand_invalid_rate <= baseline_invalid_rate
        gates["invalid_rate"] = {"pass": inv_ok, "baseline": baseline_invalid_rate, "candidate": cand_invalid_rate}

        auto_ok = cand_auto_rate <= baseline_auto_rate
        gates["auto_fallback_rate"] = {"pass": auto_ok, "baseline": baseline_auto_rate, "candidate": cand_auto_rate}

        bp_ok = cand_bp_refusal_rate <= baseline_bp_refusal_rate
        gates["boilerplate_refusal_rate"] = {"pass": bp_ok, "baseline": baseline_bp_refusal_rate, "candidate": cand_bp_refusal_rate}

        exc_ok = cand_exceptions <= baseline_exceptions
        gates["exceptions"] = {"pass": exc_ok, "baseline": baseline_exceptions, "candidate": cand_exceptions}

        if all(g["pass"] for g in gates.values()):
            best = {
                "settings": dict(cell["settings"]),
                "median_wall_time_s": med,
                "improvement_pct": round((baseline_med - med) / baseline_med * 100, 1),
                "quality": {
                    "invalid_rate": cand_invalid_rate,
                    "auto_fallback_rate": cand_auto_rate,
                    "boilerplate_refusal_rate": cand_bp_refusal_rate,
                    "exceptions": cand_exceptions,
                },
                "gates": gates,
            }
            best_med = med

    return baseline, best


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

    batch_sizes, concurrencies = _validate_matrix(batch_sizes, concurrencies)

    if not host.rstrip("/").endswith("/v1"):
        host = host.rstrip("/") + "/v1"

    from daily_brief.llm import summarizer
    orig_model = summarizer.LLM_MODEL
    summarizer.LLM_MODEL = model

    with open(fixture_path, "rb") as _fh:
        fixture_hash = hashlib.sha256(_fh.read()).hexdigest()
    with open(fixture_path, "r", encoding="utf-8") as _fh:
        _raw_data = json.load(_fh)
    fixture_capture_date = _raw_data.get("capture_date") if isinstance(_raw_data, dict) else None

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
    if warmups > 0:
        print("Warmup runs...")
        for _ in range(warmups):
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
    else:
        print("Skipping warmups.")
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
    baseline, winner = select_winner(output_cells)

    # --- Write output ---
    summarizer.LLM_MODEL = orig_model
    output = {
        "benchmark_date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "version": VERSION,
        "config": {
            "model": model,
            "host": host,
            "fixture_path": os.path.abspath(fixture_path),
        },
        "environment": {
            "resolved_model": model,
            "resolved_host": host,
            "fixture_path": os.path.abspath(fixture_path),
            "fixture_hash": fixture_hash,
            "fixture_capture_date": fixture_capture_date,
            "corpus_stories": total,
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
        print("No winner — no cell improved >= 10% over baseline while passing all quality gates")
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
    p.add_argument("--output", default=str(Path(LOG_DIR) / "llm_batch_benchmark.json"),
                     help="JSON output file path")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
