"""
Deterministic tests for the pipeline concurrency benchmark driver.

Covers benchmark override behavior, metric aggregation, phase mode
selection, JSON result shape, concurrency tracking, and provenance.
"""

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import patch


class MockStory:
    """Minimal story with extraction timing attributes."""

    def __init__(self, title="Test", link="https://example.com/a", category="Tech", context=None):
        self.title = title
        self.link = link
        self.category = category
        self.context = context
        self.summary = None
        self.pub_dt = None
        self.snippet = ""
        self.extract_fetch_time_s = None
        self.extract_parse_time_s = None
        self.extract_bytes = None


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------


class TestStatsFromList(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import _stats_from_list

        return _stats_from_list

    def test_empty_list_returns_zeros(self):
        fn = self._import()
        result = fn([])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["min"], 0.0)
        self.assertEqual(result["mean"], 0.0)

    def test_single_value(self):
        fn = self._import()
        result = fn([2.5])
        self.assertEqual(result["count"], 1)
        self.assertAlmostEqual(result["min"], 2.5)
        self.assertAlmostEqual(result["max"], 2.5)
        self.assertAlmostEqual(result["mean"], 2.5)
        self.assertAlmostEqual(result["p50"], 2.5)
        self.assertAlmostEqual(result["p95"], 2.5)
        self.assertAlmostEqual(result["p99"], 2.5)

    def test_multiple_values_sorted(self):
        fn = self._import()
        result = fn([1.0, 2.0, 3.0, 4.0, 5.0])
        self.assertEqual(result["count"], 5)
        self.assertAlmostEqual(result["min"], 1.0)
        self.assertAlmostEqual(result["max"], 5.0)
        self.assertAlmostEqual(result["mean"], 3.0)

    def test_unsorted_input(self):
        fn = self._import()
        result_sorted = fn([1.0, 2.0, 3.0])
        result_unsorted = fn([3.0, 1.0, 2.0])
        self.assertAlmostEqual(result_sorted["p50"], result_unsorted["p50"])
        self.assertAlmostEqual(result_sorted["mean"], result_unsorted["mean"])

    def test_rounds_values(self):
        fn = self._import()
        result = fn([1.123456789])
        # Values rounded to 4 decimal places
        self.assertLessEqual(len(str(result["mean"])), 7)


class TestPercentileBenchmarkCopy(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import _percentile

        return _percentile

    def test_p50(self):
        fn = self._import()
        self.assertAlmostEqual(fn([1.0, 2.0, 3.0], 50), 2.0)

    def test_p0(self):
        fn = self._import()
        self.assertAlmostEqual(fn([1.0, 2.0, 3.0], 0), 1.0)

    def test_p100(self):
        fn = self._import()
        self.assertAlmostEqual(fn([1.0, 2.0, 3.0], 100), 3.0)

    def test_empty(self):
        fn = self._import()
        self.assertEqual(fn([], 50), 0.0)

    def test_interpolated(self):
        fn = self._import()
        result = fn([10.0, 20.0], 50)
        self.assertAlmostEqual(result, 15.0)


# ---------------------------------------------------------------------------
# Extraction metrics aggregation
# ---------------------------------------------------------------------------


class TestExtractionMetrics(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import ExtractionMetrics

        return ExtractionMetrics

    def test_default_values(self):
        fn = self._import()
        m = fn()
        self.assertEqual(m.total_stories, 0)
        self.assertEqual(m.extracted_count, 0)
        self.assertEqual(m.failed_count, 0)
        self.assertEqual(m.skipped_count, 0)
        self.assertEqual(m.max_concurrency_observed, 0)

    def test_to_dict_includes_distribution_stats(self):
        fn = self._import()
        m = fn(
            total_stories=10,
            extracted_count=7,
            failed_count=1,
            skipped_count=2,
            fetch_times=[0.5, 1.0, 1.5],
            parse_times=[0.01, 0.02],
            bytes_list=[1000, 2000, 3000],
            max_concurrency_observed=4,
        )
        d = m.to_dict()
        self.assertEqual(d["total_stories"], 10)
        self.assertEqual(d["extracted_count"], 7)
        self.assertIn("fetch_time_s", d)
        self.assertIn("parse_time_s", d)
        self.assertIn("bytes", d)
        self.assertEqual(d["fetch_time_s"]["count"], 3)
        self.assertEqual(d["parse_time_s"]["count"], 2)
        self.assertEqual(d["bytes"]["count"], 3)
        self.assertEqual(d["max_concurrency_observed"], 4)
        self.assertNotIn("fetch_times", d)
        self.assertNotIn("parse_times", d)

    def test_to_dict_empty_distributions(self):
        fn = self._import()
        m = fn(total_stories=5)
        d = m.to_dict()
        self.assertEqual(d["fetch_time_s"]["count"], 0)
        self.assertEqual(d["parse_time_s"]["count"], 0)
        self.assertEqual(d["bytes"]["count"], 0)


# ---------------------------------------------------------------------------
# LoopLagMetrics
# ---------------------------------------------------------------------------


class TestLoopLagMetrics(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import LoopLagMetrics

        return LoopLagMetrics

    def test_default_values(self):
        fn = self._import()
        m = fn()
        d = m.to_dict()
        self.assertEqual(d["samples"], 0)
        self.assertEqual(d["p50_ms"], 0.0)
        self.assertEqual(d["max_ms"], 0.0)

    def test_rounded_values(self):
        fn = self._import()
        m = fn(samples=100, p50_ms=1.234567, p95_ms=5.678901)
        d = m.to_dict()
        self.assertEqual(d["p50_ms"], 1.23)
        self.assertEqual(d["p95_ms"], 5.68)


# ---------------------------------------------------------------------------
# PhaseTimings
# ---------------------------------------------------------------------------


class TestPhaseTimings(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import PhaseTimings

        return PhaseTimings

    def test_to_dict_rounds(self):
        fn = self._import()
        t = fn(phase1_s=1.234567, total_s=50.987654)
        d = t.to_dict()
        self.assertAlmostEqual(d["phase1_s"], 1.235)
        self.assertAlmostEqual(d["total_s"], 50.988)

    def test_all_phases_present(self):
        fn = self._import()
        t = fn()
        d = t.to_dict()
        expected_keys = {
            "phase1_s",
            "phase2_s",
            "phase3a_s",
            "phase3_s",
            "phase4_s",
            "phase5_s",
            "phase6_s",
            "total_s",
        }
        self.assertEqual(set(d.keys()), expected_keys)


# ---------------------------------------------------------------------------
# CellResult JSON shape
# ---------------------------------------------------------------------------


class TestCellResultShape(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import (
            CellResult,
            ExtractionMetrics,
            LoopLagMetrics,
            PhaseTimings,
        )

        return CellResult, ExtractionMetrics, LoopLagMetrics, PhaseTimings

    def test_to_dict_has_all_top_level_keys(self):
        CR, EM, LM, PT = self._import()
        r = CR(
            concurrency=4,
            phase_mode="concurrent",
            story_count=80,
            rss_counts={"total_after": 80},
            weather_ok=True,
            extraction=EM(total_stories=80, extracted_count=60),
            loop_lag=LM(samples=100, p50_ms=1.5),
            timings=PT(total_s=50.0),
            report_validation="PASS",
            harness_status="PASS",
            process_exit=0,
        )
        d = r.to_dict()
        required = {
            "concurrency",
            "phase_mode",
            "story_count",
            "rss_counts",
            "weather_ok",
            "extraction",
            "loop_lag",
            "timings",
            "report_validation",
            "harness_status",
            "harness_message",
            "process_exit",
            "config",
            "error",
        }
        self.assertTrue(required.issubset(set(d.keys())))

    def test_serializable(self):
        CR, EM, LM, PT = self._import()
        r = CR(concurrency=4, phase_mode="serial")
        json_str = json.dumps(r.to_dict(), default=str)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["concurrency"], 4)
        self.assertEqual(parsed["phase_mode"], "serial")

    def test_error_field(self):
        CR, EM, LM, PT = self._import()
        r = CR(concurrency=4, error="test error")
        d = r.to_dict()
        self.assertEqual(d["error"], "test error")


# ---------------------------------------------------------------------------
# BenchmarkRun JSON shape
# ---------------------------------------------------------------------------


class TestBenchmarkRunShape(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import BenchmarkRun

        return BenchmarkRun

    def test_to_dict_has_required_keys(self):
        fn = self._import()
        run = fn(
            started_at="2026-01-01T00:00:00Z",
            completed_at="2026-01-01T00:01:00Z",
            duration_s=60.0,
            cells=[],
        )
        d = run.to_dict()
        required = {"started_at", "completed_at", "duration_s", "provenance", "cells", "summary"}
        self.assertTrue(required.issubset(set(d.keys())))

    def test_serializable(self):
        fn = self._import()
        run = fn(cells=[{"concurrency": 1}])
        json_str = json.dumps(run.to_dict(), default=str)
        parsed = json.loads(json_str)
        self.assertEqual(len(parsed["cells"]), 1)


# ---------------------------------------------------------------------------
# Concurrency tracker
# ---------------------------------------------------------------------------


class TestConcurrencyTracker(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import _ConcurrencyTracker

        return _ConcurrencyTracker

    def _loop(self, coro):
        import asyncio

        return asyncio.get_event_loop().run_until_complete(coro)

    def test_peak_tracks_max_concurrent(self):
        fn = self._import()
        tracker = fn()

        async def _test():
            await tracker.enter()
            await tracker.enter()
            await tracker.enter()
            self.assertEqual(tracker.peak, 3)
            await tracker.exit()
            self.assertEqual(tracker.peak, 3)  # peak unchanged
            await tracker.exit()
            await tracker.exit()

        self._loop(_test())

    def test_peak_zero_initially(self):
        fn = self._import()
        tracker = fn()
        self.assertEqual(tracker.peak, 0)

    def test_peak_persists_across_entries(self):
        fn = self._import()
        tracker = fn()

        async def _test():
            for _ in range(2):
                await tracker.enter()
                await tracker.enter()
                await tracker.exit()
                await tracker.exit()
            self.assertEqual(tracker.peak, 2)

        self._loop(_test())


# ---------------------------------------------------------------------------
# run_benchmark orchestrator
# ---------------------------------------------------------------------------


class TestRunBenchmark(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import run_benchmark

        return run_benchmark

    def setUp(self):
        self._loop_policy = asyncio.get_event_loop_policy()

    def tearDown(self):
        try:
            asyncio.set_event_loop_policy(self._loop_policy)
        except Exception:
            pass

    def test_default_concurrencies(self):
        fn = self._import()

        async def _fake_cell(conc, mode, **kw):
            from daily_brief.benchmark_pipeline_concurrency import CellResult, PhaseTimings

            return CellResult(
                concurrency=conc, phase_mode=mode, timings=PhaseTimings(total_s=float(conc))
            )

        with patch(
            "daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_fake_cell
        ):
            result = fn(cells=1, warmups=0)
            concs = [c["concurrency"] for c in result.cells]
            self.assertEqual(sorted(concs), [1, 2, 4, 6, 8])

    def test_custom_concurrencies(self):
        fn = self._import()

        async def _fake_cell(conc, mode, **kw):
            from daily_brief.benchmark_pipeline_concurrency import CellResult, PhaseTimings

            return CellResult(
                concurrency=conc, phase_mode=mode, timings=PhaseTimings(total_s=float(conc))
            )

        with patch(
            "daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_fake_cell
        ):
            result = fn(concurrencies=[1, 8], cells=1, warmups=0)
            concs = [c["concurrency"] for c in result.cells]
            self.assertEqual(sorted(concs), [1, 8])

    def test_phase_mode_validation(self):
        fn = self._import()
        with self.assertRaises(ValueError):
            fn(phase_mode="invalid")

    def test_phase_mode_serial(self):
        fn = self._import()
        actual_mode = []

        async def _capture(conc, mode="concurrent", **kw):
            actual_mode.append(mode)
            from daily_brief.benchmark_pipeline_concurrency import CellResult, PhaseTimings

            return CellResult(concurrency=conc, phase_mode=mode, timings=PhaseTimings(total_s=1.0))

        with patch("daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_capture):
            fn(concurrencies=[2], cells=1, warmups=0, phase_mode="serial")
        self.assertEqual(actual_mode, ["serial"])

    def test_phase_mode_concurrent(self):
        fn = self._import()
        actual_mode = []

        async def _capture(conc, mode="concurrent", **kw):
            actual_mode.append(mode)
            from daily_brief.benchmark_pipeline_concurrency import CellResult, PhaseTimings

            return CellResult(concurrency=conc, phase_mode=mode, timings=PhaseTimings(total_s=1.0))

        with patch("daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_capture):
            fn(concurrencies=[2], cells=1, warmups=0, phase_mode="concurrent")
        self.assertEqual(actual_mode, ["concurrent"])

    def test_cells_count(self):
        fn = self._import()

        async def _fake_cell(conc, mode, **kw):
            from daily_brief.benchmark_pipeline_concurrency import CellResult, PhaseTimings

            return CellResult(concurrency=conc, phase_mode=mode, timings=PhaseTimings(total_s=1.0))

        with patch(
            "daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_fake_cell
        ):
            result = fn(concurrencies=[2, 4], cells=3, warmups=0)
            self.assertEqual(len(result.cells), 6)

    def test_warmups_not_recorded(self):
        fn = self._import()
        call_count = [0]

        async def _counted(conc, mode, **kw):
            call_count[0] += 1
            from daily_brief.benchmark_pipeline_concurrency import CellResult, PhaseTimings

            return CellResult(concurrency=conc, phase_mode=mode, timings=PhaseTimings(total_s=1.0))

        with patch("daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_counted):
            result = fn(concurrencies=[2], cells=1, warmups=2)
            # 2 warmups + 1 measured = 3 total calls
            self.assertEqual(call_count[0], 3)
            # Only 1 measured result
            self.assertEqual(len(result.cells), 1)

    def test_output_file_json(self):
        fn = self._import()

        async def _fake_cell(conc, mode, **kw):
            from daily_brief.benchmark_pipeline_concurrency import CellResult, PhaseTimings

            return CellResult(concurrency=conc, phase_mode=mode, timings=PhaseTimings(total_s=1.0))

        with (
            tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf,
            patch(
                "daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_fake_cell
            ),
        ):
            tmp_path = tf.name
            try:
                fn(concurrencies=[1], cells=1, warmups=0, output_file=tmp_path)
                with open(tmp_path) as f:
                    data = json.load(f)
                self.assertIn("cells", data)
                self.assertIn("provenance", data)
                self.assertEqual(len(data["cells"]), 1)
                self.assertEqual(data["cells"][0]["concurrency"], 1)
            finally:
                os.unlink(tmp_path)

    def test_summary_computed(self):
        fn = self._import()

        async def _fake_cell(conc, mode, **kw):
            from daily_brief.benchmark_pipeline_concurrency import CellResult, PhaseTimings

            return CellResult(
                concurrency=conc, phase_mode=mode, timings=PhaseTimings(total_s=float(conc) * 10)
            )

        with patch(
            "daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_fake_cell
        ):
            result = fn(concurrencies=[1, 4], cells=1, warmups=0)
        self.assertIn("total_cells", result.summary)
        self.assertIn("medians", result.summary)
        self.assertEqual(result.summary["total_cells"], 2)

    def test_cell_index_assigned(self):
        fn = self._import()

        async def _fake_cell(conc, mode, **kw):
            from daily_brief.benchmark_pipeline_concurrency import CellResult, PhaseTimings

            return CellResult(concurrency=conc, phase_mode=mode, timings=PhaseTimings(total_s=1.0))

        with patch(
            "daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_fake_cell
        ):
            result = fn(concurrencies=[2], cells=3, warmups=0)
        indices = [c["cell_index"] for c in result.cells]
        self.assertEqual(indices, [0, 1, 2])

    def test_provenance_present(self):
        fn = self._import()

        async def _fake_cell(conc, mode, **kw):
            from daily_brief.benchmark_pipeline_concurrency import CellResult, PhaseTimings

            return CellResult(concurrency=conc, phase_mode=mode, timings=PhaseTimings(total_s=1.0))

        with patch(
            "daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_fake_cell
        ):
            result = fn(concurrencies=[1], cells=1, warmups=0)
        prov = result.provenance
        self.assertIn("version", prov)
        self.assertIn("llm_model", prov)
        self.assertIn("timestamp", prov)


# ---------------------------------------------------------------------------
# _build_provenance
# ---------------------------------------------------------------------------


class TestBuildProvenance(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import _build_provenance

        return _build_provenance

    def test_has_version(self):
        fn = self._import()
        p = fn()
        self.assertIn("version", p)

    def test_has_llm_config(self):
        fn = self._import()
        p = fn()
        self.assertIn("llm_model", p)
        self.assertIn("batch_size", p)
        self.assertIn("batch_concurrency", p)

    def test_has_weather(self):
        fn = self._import()
        p = fn()
        self.assertIn("weather", p)
        self.assertIn("lat", p["weather"])
        self.assertIn("lon", p["weather"])

    def test_has_categories(self):
        fn = self._import()
        p = fn()
        self.assertIn("categories", p)
        self.assertIsInstance(p["categories"], int)

    def test_has_timestamp(self):
        fn = self._import()
        p = fn()
        self.assertIn("timestamp", p)
        # Should be ISO format
        self.assertIn("T", p["timestamp"])


# ---------------------------------------------------------------------------
# _extract_story_metrics
# ---------------------------------------------------------------------------


class TestExtractStoryMetrics(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import (
            _extract_story_metrics,
            _LatencyTracker,
        )

        return _extract_story_metrics, _LatencyTracker

    def test_extracts_values(self):
        fn, LT = self._import()
        story = MockStory(
            context="some text",
        )
        story.extract_fetch_time_s = 0.5
        story.extract_parse_time_s = 0.02
        story.extract_bytes = 2048

        tracker = fn(story)
        self.assertEqual(tracker.fetch, 0.5)
        self.assertEqual(tracker.parse, 0.02)
        self.assertEqual(tracker.bytes, 2048)

    def test_none_for_missing(self):
        fn, LT = self._import()
        story = object()
        tracker = fn(story)
        self.assertIsNone(tracker.fetch)
        self.assertIsNone(tracker.parse)
        self.assertIsNone(tracker.bytes)


# ---------------------------------------------------------------------------
# CLI subcommand
# ---------------------------------------------------------------------------


class TestBenchmarkCLI(unittest.TestCase):
    def _import(self):
        from daily_brief.benchmark_pipeline_concurrency import (
            build_benchmark_parser,
            cmd_benchmark,
        )

        return build_benchmark_parser, cmd_benchmark

    def setUp(self):
        self._loop_policy = asyncio.get_event_loop_policy()

    def tearDown(self):
        try:
            asyncio.set_event_loop_policy(self._loop_policy)
        except Exception:
            pass

    def test_parser_default_concurrency(self):
        bp, cb = self._import()
        parser = bp()
        args = parser.parse_args([])
        self.assertEqual(args.concurrency, [1, 2, 4])

    def test_parser_custom_concurrency(self):
        bp, cb = self._import()
        parser = bp()
        args = parser.parse_args(["--concurrency", "3", "6"])
        self.assertEqual(args.concurrency, [3, 6])

    def test_parser_phase_mode(self):
        bp, cb = self._import()
        parser = bp()
        args = parser.parse_args(["--phase-mode", "serial"])
        self.assertEqual(args.phase_mode, "serial")

    def test_parser_cells(self):
        bp, cb = self._import()
        parser = bp()
        args = parser.parse_args(["--cells", "5"])
        self.assertEqual(args.cells, 5)

    def test_parser_warmups(self):
        bp, cb = self._import()
        parser = bp()
        args = parser.parse_args(["--warmups", "2"])
        self.assertEqual(args.warmups, 2)

    def test_cmd_benchmark_runs(self):
        bp, cb = self._import()

        async def _fake_cell(conc, mode, **kw):
            from daily_brief.benchmark_pipeline_concurrency import CellResult, PhaseTimings

            return CellResult(concurrency=conc, phase_mode=mode, timings=PhaseTimings(total_s=1.0))

        with (
            patch(
                "daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_fake_cell
            ),
            patch("daily_brief.benchmark_pipeline_concurrency.run_benchmark") as mock_run,
        ):
            from daily_brief.benchmark_pipeline_concurrency import BenchmarkRun

            mock_run.return_value = BenchmarkRun(cells=[{"concurrency": 1}], duration_s=1.0)
            exit_code = cb(["--concurrency", "1", "--cells", "1"])
        self.assertEqual(exit_code, 0)


# ---------------------------------------------------------------------------
# Integration: JSON shape end-to-end
# ---------------------------------------------------------------------------


class TestJSONResultEndToEnd(unittest.TestCase):
    """Verify the full JSON output is parseable and has expected structure."""

    def setUp(self):
        self._loop_policy = asyncio.get_event_loop_policy()

    def tearDown(self):
        try:
            asyncio.set_event_loop_policy(self._loop_policy)
        except Exception:
            pass

    def test_full_run_json_shape(self):
        from daily_brief.benchmark_pipeline_concurrency import run_benchmark

        async def _fake_cell(conc, mode, **kw):
            from daily_brief.benchmark_pipeline_concurrency import (
                CellResult,
                ExtractionMetrics,
                LoopLagMetrics,
                PhaseTimings,
            )

            return CellResult(
                concurrency=conc,
                phase_mode=mode,
                story_count=80,
                rss_counts={"total_after": 80},
                weather_ok=True,
                extraction=ExtractionMetrics(
                    total_stories=80,
                    extracted_count=60,
                    fetch_times=[0.3, 0.5, 0.7],
                    parse_times=[0.01, 0.02],
                    bytes_list=[1000, 2000],
                    max_concurrency_observed=conc,
                ),
                loop_lag=LoopLagMetrics(
                    samples=50,
                    p50_ms=1.2,
                    p95_ms=5.0,
                    p99_ms=8.0,
                    max_ms=12.0,
                    min_ms=0.1,
                    mean_ms=2.0,
                ),
                timings=PhaseTimings(
                    phase1_s=5.0,
                    phase2_s=6.0,
                    phase3a_s=3.0,
                    phase3_s=30.0,
                    phase4_s=0.5,
                    phase5_s=0.3,
                    phase6_s=2.0,
                    total_s=float(conc) * 10,
                ),
                report_validation="PASS",
                harness_status="WARN",
                harness_message="test",
                process_exit=1,
            )

        with (
            tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf,
            patch(
                "daily_brief.benchmark_pipeline_concurrency._run_benchmark_cell", new=_fake_cell
            ),
        ):
            tmp_path = tf.name
            try:
                result = run_benchmark(
                    concurrencies=[2, 4],
                    cells=2,
                    warmups=0,
                    phase_mode="concurrent",
                    output_file=tmp_path,
                )

                # Verify in-memory result
                self.assertEqual(len(result.cells), 4)

                # Verify file was written and parseable
                with open(tmp_path) as f:
                    data = json.load(f)

                # Top-level structure
                self.assertIn("provenance", data)
                self.assertIn("cells", data)
                self.assertIn("summary", data)
                self.assertIn("started_at", data)

                # Each cell has required keys
                for cell in data["cells"]:
                    self.assertIn("concurrency", cell)
                    self.assertIn("phase_mode", cell)
                    self.assertIn("extraction", cell)
                    self.assertIn("timings", cell)
                    self.assertIn("loop_lag", cell)
                    self.assertIn("report_validation", cell)
                    self.assertIn("harness_status", cell)
                    self.assertIn("cell_index", cell)

                    # Extraction stats
                    ext = cell["extraction"]
                    self.assertIn("fetch_time_s", ext)
                    self.assertIn("parse_time_s", ext)
                    self.assertIn("bytes", ext)
                    self.assertIn("max_concurrency_observed", ext)

                    # Timings
                    timings = cell["timings"]
                    self.assertIn("total_s", timings)

                    # Loop lag
                    lag = cell["loop_lag"]
                    self.assertIn("samples", lag)
                    self.assertIn("p50_ms", lag)

            finally:
                os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
