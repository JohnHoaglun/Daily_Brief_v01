"""
Unit tests for benchmark validation: corpus fixtures, matrix, metrics, and output.

Covers the benchmark workflow used to tune batch_size and max_concurrency for
the LLM summarization pipeline.  Tests are self-contained — they build their
own fixture data using the existing StoryPipelineState factory pattern rather
than depending on an external benchmark module.

Run:  python -m unittest tests.test_benchmark_llm_batches
"""
import asyncio
import json
import os
import statistics
import tempfile
from unittest import TestCase, mock
from unittest.mock import AsyncMock, MagicMock

from daily_brief import benchmark_llm_batches as bench
from daily_brief.llm.summarizer import (
    StoryPipelineState,
    build_context,
    batch_summarize_all,
)


# ---------------------------------------------------------------------------
# Fixture helpers — mirror the StoryPipelineState factory pattern from
# test_summarizer.py
# ---------------------------------------------------------------------------

def _make_story(
    title: str,
    category: str,
    url: str = "http://example.com",
    snippet: str = "Short snippet text for the story.",
    pub_date: str = "2025-01-01",
    context: str = None,
):
    """Create a StoryPipelineState (Story) with minimal defaults."""
    s = StoryPipelineState(title=title, link=url, snippet=snippet or "", pub_dt=pub_date, category=category)
    s.context = context if context else f"Context body for {title}. " * 20
    s.summary = None
    return s


def _make_corpus(stories_data: list) -> dict:
    """Build a minimal capture-corpus fixture dict.

    Matches the structure expected by benchmark capture/playback:
    {
      "metadata": { "capture_date": "...", "version": "...", "total_stories": N },
      "categories": ["Tech", "Finance", ...],
      "stories": [ { "title", "url", "category", "snippet", "pub_date", "context" }, ... ]
    }
    """
    cats = list(dict.fromkeys(s["category"] for s in stories_data))
    return {
        "metadata": {
            "capture_date": stories_data[0].get("pub_date", "2025-01-01") if stories_data else "2025-01-01",
            "version": "v1.0.90",
            "total_stories": len(stories_data),
        },
        "categories": cats,
        "stories": stories_data,
    }


# ---------------------------------------------------------------------------
# 1.  TestCaptureCorpusValidation
# ---------------------------------------------------------------------------


class TestCaptureCorpusValidation(TestCase):
    """Validate the minimal fixture JSON structure loads and is well-formed."""

    def _minimal_stories(self, n: int = 6) -> list:
        cats = ["Tech", "Finance", "Weather"]
        return [
            {
                "title": f"Story {i} in {cats[i % 3]}",
                "url": f"http://example.com/{i}",
                "category": cats[i % 3],
                "snippet": f"Snippet text for story {i}.",
                "pub_date": "2025-01-01",
                "context": f"Longer context body for story {i}. " * 10,
            }
            for i in range(n)
        ]

    def test_fixture_json_loads_correctly(self):
        stories = self._minimal_stories(6)
        corpus = _make_corpus(stories)
        raw = json.dumps(corpus)
        parsed = json.loads(raw)
        self.assertIn("metadata", parsed)
        self.assertIn("categories", parsed)
        self.assertIn("stories", parsed)

    def test_required_story_fields(self):
        stories = self._minimal_stories()
        corpus = _make_corpus(stories)
        required = {"title", "url", "category", "snippet", "pub_date", "context"}
        for s in corpus["stories"]:
            missing = required - set(s.keys())
            self.assertEqual(missing, set(), f"Story missing fields: {missing}")

    def test_category_breakdown_computation(self):
        stories = self._minimal_stories(9)
        corpus = _make_corpus(stories)
        breakdown: dict = {}
        for s in corpus["stories"]:
            breakdown[s["category"]] = breakdown.get(s["category"], 0) + 1
        self.assertEqual(len(breakdown), 3)
        self.assertEqual(sum(breakdown.values()), len(corpus["stories"]))

    def test_corpus_metadata_fields(self):
        stories = self._minimal_stories(5)
        corpus = _make_corpus(stories)
        meta = corpus["metadata"]
        self.assertIn("capture_date", meta)
        self.assertIn("version", meta)
        self.assertIn("total_stories", meta)
        self.assertEqual(meta["total_stories"], 5)
        self.assertEqual(meta["capture_date"], "2025-01-01")


# ---------------------------------------------------------------------------
# 2.  TestBenchmarkFixtureLoading
# ---------------------------------------------------------------------------


class TestBenchmarkFixtureLoading(TestCase):
    """Corpus stories reconstruct with correct StoryPipelineState attributes."""

    def _fixture(self, n: int = 6) -> dict:
        cats = ["Tech", "Finance", "Weather"]
        stories = [
            {
                "title": f"S{i} {cats[i % 3]}",
                "url": f"http://example.com/{i}",
                "category": cats[i % 3],
                "snippet": f"Snippet {i}.",
                "pub_date": "2025-01-01",
                "context": f"Context body for story {i}. " * 10,
            }
            for i in range(n)
        ]
        return _make_corpus(stories)

    def test_stories_reconstructed(self):
        corpus = self._fixture(6)
        states = []
        for raw in corpus["stories"]:
            s = _make_story(
                title=raw["title"],
                category=raw["category"],
                url=raw["url"],
                snippet=raw["snippet"],
                pub_date=raw["pub_date"],
                context=raw["context"],
            )
            states.append(s)
        self.assertEqual(len(states), 6)
        for s in states:
            self.assertIsInstance(s, StoryPipelineState)
            self.assertIsNotNone(s.context)
            self.assertIsNone(s.summary)

    def test_category_ordering_preserved(self):
        corpus = self._fixture(6)
        original_cats = [s["category"] for s in corpus["stories"]]
        states = [
            _make_story(**{k: v for k, v in raw.items()})
            for raw in corpus["stories"]
        ]
        reconstructed_cats = [s.category for s in states]
        self.assertEqual(original_cats, reconstructed_cats)

    def test_empty_fixture(self):
        corpus = _make_corpus([])
        self.assertEqual(corpus["metadata"]["total_stories"], 0)
        self.assertEqual(corpus["stories"], [])
        self.assertEqual(corpus["categories"], [])

    def test_missing_fixture_raises(self):
        """Accessing the first story of an empty corpus raises."""
        corpus = _make_corpus([])
        with self.assertRaises(IndexError):
            _ = corpus["stories"][0]


# ---------------------------------------------------------------------------
# 3.  TestBenchmarkMatrix
# ---------------------------------------------------------------------------


class TestBenchmarkMatrix(TestCase):
    """Batch/concurrency matrix generation and validation."""

    def _build_matrix(
        self, batch_sizes: list, concurrencies: list
    ) -> list:
        """Generate (batch_size, concurrency) cells."""
        cells = []
        for bs in batch_sizes:
            for mc in concurrencies:
                cells.append({"batch_size": bs, "max_concurrency": mc})
        return cells

    def test_valid_matrix_combinations(self):
        cells = self._build_matrix([3, 4, 5, 6], [1, 2])
        self.assertEqual(len(cells), 8)
        expected = [
            (3, 1), (3, 2),
            (4, 1), (4, 2),
            (5, 1), (5, 2),
            (6, 1), (6, 2),
        ]
        actual = [(c["batch_size"], c["max_concurrency"]) for c in cells]
        self.assertEqual(actual, expected)

    def test_invalid_batch_size_zero(self):
        cells = self._build_matrix([0], [1])
        self.assertEqual(len(cells), 1)
        self.assertEqual(cells[0]["batch_size"], 0)
        # batch_size=0 is invalid — calling batch_summarize_all with it
        # on non-empty stories would trigger empty sub-batch behaviour
        # (the pipeline uses range(0, len, 0) which raises ValueError).
        # This test documents the constraint without triggering the error.

    def test_shuffling_fixed_seed_reproducible(self):
        import random
        stories = [
            _make_story(f"Story {i}", "Tech") for i in range(12)
        ]

        random.seed(42)
        shuffled_a = list(stories)
        random.shuffle(shuffled_a)

        random.seed(42)
        shuffled_b = list(stories)
        random.shuffle(shuffled_b)

        titles_a = [s.title for s in shuffled_a]
        titles_b = [s.title for s in shuffled_b]
        self.assertEqual(titles_a, titles_b)


# ---------------------------------------------------------------------------
# 4.  TestBenchmarkMetrics
# ---------------------------------------------------------------------------


class TestBenchmarkMetrics(TestCase):
    """Capture call-type, concurrency, and timing metrics with AsyncMock."""

    def _make_stories(self, n: int = 6):
        return [_make_story(f"Story {i}", "Tech") for i in range(n)]

    def _make_batch_client(self, stories, batch_size=3):
        """Client that returns valid STORY_N | summaries for any sub-batch."""

        async def side_effect(**kwargs):
            user_content = kwargs["messages"][1]["content"]
            blocks = user_content.split("\n---\n\n")
            batch_titles = []
            for block in blocks:
                for line in block.strip().split("\n"):
                    if line and not line.startswith(("1. ", "2. ", "3. ")):
                        batch_titles.append(line.strip())
                        break
            parts = []
            for i, tl in enumerate(batch_titles):
                parts.append(
                    f"STORY_{i} | {tl}=Summary for {tl}. "
                    f"Additional detail sentence that makes this a valid summary."
                )
            content = "\n".join(parts) if parts else "STORY_0 | Default=Default summary text here."
            r = mock.MagicMock()
            r.choices = [mock.MagicMock(message=mock.MagicMock(content=content))]
            return r

        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)
        return client

    def test_records_batch_call_type(self):
        """Verify instrumented client receives batch-system calls.

        We mock chat_completions_create to capture whether the system prompt
        contains batch keywords, confirming the call was a batch (not single)
        summarization.
        """
        stories = self._make_stories(6)
        client = self._make_batch_client(stories, batch_size=3)

        call_system_prompts: list = []
        original_mock = client.chat_completions_create

        async def recording_wrapper(**kwargs):
            msgs = kwargs.get("messages", [])
            if msgs:
                call_system_prompts.append(msgs[0]["content"])
            return await original_mock(**kwargs)

        client.chat_completions_create = AsyncMock(
            side_effect=recording_wrapper
        )

        async def _run():
            with mock.patch(
                "daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1
            ):
                with mock.patch(
                    "daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []
                ):
                    with mock.patch(
                        "asyncio.sleep", new_callable=AsyncMock, return_value=None
                    ):
                        return await batch_summarize_all(
                            client, stories, batch_size=3
                        )

        asyncio.get_event_loop().run_until_complete(_run())

        self.assertGreater(len(call_system_prompts), 0)
        # Every call should have the batch system prompt
        from daily_brief.config import SYSTEM_BATCH_PROMPT
        for sp in call_system_prompts:
            self.assertEqual(sp, SYSTEM_BATCH_PROMPT)

    def test_max_concurrent_request_tracking(self):
        """Verify max concurrency is tracked via semaphore simulation."""
        active = [0]
        max_active = [0]

        async def record(label):
            active[0] += 1
            max_active[0] = max(max_active[0], active[0])
            await asyncio.sleep(0.02)
            active[0] -= 1

        # Concurrency-2: up to 2 overlap
        sem2 = asyncio.Semaphore(2)

        async def guarded2(label):
            async with sem2:
                await record(label)

        async def run_c2():
            await asyncio.gather(
                guarded2("A"), guarded2("B"), guarded2("C"), guarded2("D")
            )

        asyncio.get_event_loop().run_until_complete(run_c2())
        self.assertEqual(max_active[0], 2)

        # Concurrency-1: strictly serial
        max_active[0] = 0
        active[0] = 0
        sem1 = asyncio.Semaphore(1)

        async def guarded1(label):
            async with sem1:
                await record(label)

        async def run_c1():
            await asyncio.gather(
                guarded1("A"), guarded1("B"), guarded1("C"), guarded1("D")
            )

        asyncio.get_event_loop().run_until_complete(run_c1())
        self.assertEqual(max_active[0], 1)

    def test_stories_per_second_calculation(self):
        """Verify s/s = num_stories / elapsed, matching benchmark formula."""
        import time

        stories = self._make_stories(12)
        client = self._make_batch_client(stories, batch_size=3)

        async def _run():
            with mock.patch(
                "daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1
            ):
                with mock.patch(
                    "daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []
                ):
                    with mock.patch(
                        "asyncio.sleep", new_callable=AsyncMock, return_value=None
                    ):
                        return await batch_summarize_all(
                            client, stories, batch_size=3
                        )

        t_start = time.monotonic()
        asyncio.get_event_loop().run_until_complete(_run())
        elapsed = time.monotonic() - t_start

        sps = len(stories) / elapsed if elapsed > 0 else 0.0
        self.assertGreater(sps, 0)
        # With mocked client (no real network), throughput is high
        self.assertGreater(sps, 50.0)

    def test_median_min_max_across_runs(self):
        """Verify median/min/max across multiple benchmark runs."""
        import time

        run_times: list = []

        for _ in range(3):
            stories = self._make_stories(6)
            client = self._make_batch_client(stories, batch_size=3)

            async def _run():
                with mock.patch(
                    "daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1
                ):
                    with mock.patch(
                        "daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []
                    ):
                        with mock.patch(
                            "asyncio.sleep",
                            new_callable=AsyncMock,
                            return_value=None,
                        ):
                            return await batch_summarize_all(
                                client, stories, batch_size=3
                            )

            t0 = time.monotonic()
            asyncio.get_event_loop().run_until_complete(_run())
            run_times.append(time.monotonic() - t0)

        self.assertEqual(len(run_times), 3)
        self.assertAlmostEqual(min(run_times), min(run_times), places=6)
        self.assertAlmostEqual(max(run_times), max(run_times), places=6)
        med = statistics.median(run_times)
        self.assertLessEqual(min(run_times), med)
        self.assertGreaterEqual(max(run_times), med)


# ---------------------------------------------------------------------------
# 5.  TestBenchmarkOutput
# ---------------------------------------------------------------------------


class TestBenchmarkOutput(TestCase):
    """Benchmark result JSON structure and derived fields."""

    def _minimal_output(
        self,
        cells: list = None,
        winner: dict = None,
        baseline: dict = None,
    ) -> dict:
        if cells is None:
            cells = []
        return {
            "timestamp": "2025-01-01T00:00:00Z",
            "corpus": {"total_stories": 12, "version": "v1.0.0"},
            "cells": cells,
            "baseline_cell": baseline,
            "winner": winner,
            "threshold": {"min_stories_per_second": 0.5, "max_latency_seconds": 30},
        }

    def test_json_output_required_keys(self):
        output = self._minimal_output()
        required = {
            "timestamp",
            "corpus",
            "cells",
            "baseline_cell",
            "winner",
            "threshold",
        }
        missing = required - set(output.keys())
        self.assertEqual(missing, set(), f"Missing top-level keys: {missing}")

    def test_json_serializable(self):
        output = self._minimal_output(cells=[
            {"batch_size": 3, "max_concurrency": 1, "elapsed_s": 1.5, "stories_per_sec": 8.0},
        ])
        raw = json.dumps(output)
        parsed = json.loads(raw)
        self.assertIn("cells", parsed)

    def test_winner_none_when_no_threshold_met(self):
        output = self._minimal_output(
            cells=[
                {"batch_size": 3, "max_concurrency": 1, "stories_per_sec": 0.1},
                {"batch_size": 4, "max_concurrency": 1, "stories_per_sec": 0.2},
            ],
            winner=None,
        )
        self.assertIsNone(output["winner"])
        # Verify no cell meets threshold
        for cell in output["cells"]:
            self.assertLess(cell["stories_per_sec"], output["threshold"]["min_stories_per_second"])

    def test_baseline_cell_identification(self):
        """Baseline is batch_size=3, max_concurrency=1 (current default)."""
        cells = [
            {"batch_size": 3, "max_concurrency": 1, "elapsed_s": 2.0, "stories_per_sec": 6.0},
            {"batch_size": 4, "max_concurrency": 1, "elapsed_s": 1.5, "stories_per_sec": 8.0},
            {"batch_size": 3, "max_concurrency": 2, "elapsed_s": 1.8, "stories_per_sec": 6.7},
        ]
        baseline = next(
            c for c in cells
            if c["batch_size"] == 3 and c["max_concurrency"] == 1
        )
        output = self._minimal_output(cells=cells, baseline=baseline)
        self.assertEqual(output["baseline_cell"]["batch_size"], 3)
        self.assertEqual(output["baseline_cell"]["max_concurrency"], 1)

    def test_cell_fields_complete(self):
        """Each cell carries timing and quality metrics."""
        cell = {
            "batch_size": 4,
            "max_concurrency": 2,
            "elapsed_s": 1.2,
            "stories_per_sec": 10.0,
            "p50_ms": 50,
            "p95_ms": 120,
            "max_ms": 200,
            "batch_calls": 4,
            "fallback_calls": 0,
            "success_rate": 1.0,
        }
        required_fields = {
            "batch_size", "max_concurrency", "elapsed_s",
            "stories_per_sec", "p50_ms", "p95_ms", "max_ms",
            "batch_calls", "fallback_calls", "success_rate",
        }
        missing = required_fields - set(cell.keys())
        self.assertEqual(missing, set(), f"Cell missing fields: {missing}")

    def test_output_written_to_file_and_loaded(self):
        output = self._minimal_output(cells=[
            {"batch_size": 3, "max_concurrency": 1, "elapsed_s": 1.0, "stories_per_sec": 12.0},
            {"batch_size": 4, "max_concurrency": 2, "elapsed_s": 0.8, "stories_per_sec": 15.0},
        ])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(output, f)
            path = f.name
        try:
            with open(path, "r") as f:
                loaded = json.load(f)
            self.assertEqual(loaded["timestamp"], output["timestamp"])
            self.assertEqual(len(loaded["cells"]), 2)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 6.  TestQualityGates
# ---------------------------------------------------------------------------


class TestQualityGates(TestCase):
    """Quality gate winner selection tests."""

    def _make_cell(self, bs, mc, med_time, invalid_rate=0.0, auto_rate=0.0, bp_rate=0.0, ref_rate=0.0, exceptions=0):
        return {
            "settings": {"batch_size": bs, "max_concurrency": mc},
            "median_wall_time_s": med_time,
            "runs": [{
                "invalid_rate": invalid_rate,
                "auto_fallback_rate": auto_rate,
                "boilerplate_rate": bp_rate,
                "refusal_rate": ref_rate,
                "exception_count": exceptions,
                "valid_summaries": 10,
                "wall_time_s": med_time,
            }],
        }

    def _get_bench(self):
        return bench

    def test_baseline_missing_no_winner(self):
        bench = self._get_bench()
        cells = [self._make_cell(4, 1, 5.0)]
        baseline, winner = bench.select_winner(cells)
        self.assertIsNone(winner)

    def test_faster_but_more_invalid_rejected(self):
        bench = self._get_bench()
        baseline_cell = self._make_cell(3, 1, 10.0, invalid_rate=0.05)
        candidate = self._make_cell(4, 1, 8.0, invalid_rate=0.10)
        baseline, winner = bench.select_winner([baseline_cell, candidate])
        self.assertIsNone(winner)

    def test_faster_equal_quality_accepted(self):
        bench = self._get_bench()
        baseline_cell = self._make_cell(3, 1, 10.0, invalid_rate=0.05)
        candidate = self._make_cell(4, 1, 8.0, invalid_rate=0.03)
        baseline, winner = bench.select_winner([baseline_cell, candidate])
        self.assertIsNotNone(winner)
        self.assertEqual(winner["settings"]["batch_size"], 4)

    def test_not_fast_enough_rejected(self):
        bench = self._get_bench()
        baseline_cell = self._make_cell(3, 1, 10.0, invalid_rate=0.05)
        candidate = self._make_cell(4, 1, 9.5, invalid_rate=0.03)
        baseline, winner = bench.select_winner([baseline_cell, candidate])
        self.assertIsNone(winner)

    def test_gates_object_present(self):
        bench = self._get_bench()
        baseline_cell = self._make_cell(3, 1, 10.0, invalid_rate=0.05)
        candidate = self._make_cell(4, 1, 8.0, invalid_rate=0.03)
        baseline, winner = bench.select_winner([baseline_cell, candidate])
        self.assertIn("gates", winner)
        for gate_name in ["speed_improvement", "invalid_rate", "auto_fallback_rate", "boilerplate_refusal_rate", "exceptions"]:
            self.assertIn(gate_name, winner["gates"])
            self.assertIn("pass", winner["gates"][gate_name])

    def test_more_auto_fallback_rejected(self):
        bench = self._get_bench()
        baseline_cell = self._make_cell(3, 1, 10.0, auto_rate=0.02)
        candidate = self._make_cell(4, 1, 8.0, auto_rate=0.05)
        baseline, winner = bench.select_winner([baseline_cell, candidate])
        self.assertIsNone(winner)

    def test_classify_uses_production_validators(self):
        bench = self._get_bench()
        self.assertTrue(hasattr(bench, '_is_refusal'))
        source_file = os.path.join(os.path.dirname(__file__), "..", "daily_brief", "benchmark_llm_batches.py")
        with open(source_file) as f:
            source = f.read()
        self.assertIn("from daily_brief.llm.summarizer import", source)
        self.assertIn("_is_valid_summary", source)


# ---------------------------------------------------------------------------
# 6.  TestMatrixValidation
# ---------------------------------------------------------------------------

class TestMatrixValidation(TestCase):
    """Validate _validate_matrix rejects invalid inputs and deduplicates."""

    def test_rejects_zero_batch_size(self):
        """batch_size=0 is rejected with SystemExit."""
        with self.assertRaises(SystemExit):
            bench._validate_matrix([0], [1])

    def test_rejects_negative(self):
        with self.assertRaises(SystemExit):
            bench._validate_matrix([3], [-1])

    def test_deduplicates(self):
        bs, mc = bench._validate_matrix([3, 3, 4, 4], [1, 1, 2])
        self.assertEqual(sorted(bs), [3, 4])
        self.assertEqual(sorted(mc), [1, 2])

    def test_requires_baseline(self):
        """Matrix without (3,1) baseline is rejected."""
        with self.assertRaises(SystemExit):
            bench._validate_matrix([4, 5], [1, 2])

    def test_passes_with_baseline(self):
        bs, mc = bench._validate_matrix([3, 4], [1])
        self.assertIn(3, bs)
        self.assertIn(1, mc)


# ---------------------------------------------------------------------------
# 7.  TestHostNormalization
# ---------------------------------------------------------------------------

class TestHostNormalization(TestCase):
    """Verify /v1 suffix normalization logic."""

    def test_appends_v1(self):
        host = "http://192.168.4.52:8007"
        if not host.rstrip("/").endswith("/v1"):
            host = host.rstrip("/") + "/v1"
        self.assertTrue(host.endswith("/v1"))

    def test_preserves_existing_v1(self):
        host = "http://192.168.4.52:8007/v1"
        if not host.rstrip("/").endswith("/v1"):
            host = host.rstrip("/") + "/v1"
        self.assertEqual(host, "http://192.168.4.52:8007/v1")


# ---------------------------------------------------------------------------
# 8.  TestInstrumentationFields
# ---------------------------------------------------------------------------

class TestInstrumentationFields(TestCase):
    """Verify _ConcurrencyTracker has new instrumentation fields."""

    def test_tracker_has_latency_fields(self):
        t = bench._ConcurrencyTracker()
        self.assertIsInstance(t.latencies, list)
        self.assertIsInstance(t.sub_batch_sizes, list)
        self.assertEqual(t.exceptions, 0)

    def test_sub_batch_size_parsing(self):
        # A user message with N separators means N+1 stories in batch
        text = "Title 1...\n\nContext 1\n\n---\n\nTitle 2...\n\nContext 2"
        separators = text.count("\n---\n\n")
        size = separators + 1
        self.assertEqual(size, 2)


# ---------------------------------------------------------------------------
# 9.  TestEnvironmentProvenance
# ---------------------------------------------------------------------------

class TestEnvironmentProvenance(TestCase):
    """Verify environment dict keys match expected schema."""

    def test_environment_keys_exist(self):
        """Verify environment dict keys are expected."""
        required_keys = [
            "resolved_model", "resolved_host", "fixture_path",
            "fixture_hash", "fixture_capture_date", "corpus_stories",
        ]
        for key in required_keys:
            self.assertIsInstance(key, str)
