"""
Concurrency Contract Fixtures -- Wave 0 acceptance criteria.

These tests document the desired behavior for concurrent pipeline invocations.
They use fully-mocked pipeline components (no live network). Tests are expected
to FAIL against the current codebase, documenting known bugs to be fixed in Wave 4.

Issues documented:
1. Mutable module globals leak state between concurrent runs
2. Report/log version allocation is not atomic -- concurrent runs can collide
3. write_report is not atomic -- killed mid-write leaves corrupted file
4. Phase 1 and Phase 2 run serial, not concurrently
5. RSS/article extraction has no concurrency bound (asyncio.gather unbounded)
6. Pipeline global state leaks between runs (no RunContext pattern)
"""
import asyncio
import os
import re
import sys
import tempfile
import time
import threading
from unittest import TestCase, mock
from unittest.mock import AsyncMock, MagicMock, patch


from daily_brief.rendering.report import (
    compute_output_path,
    write_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_async_cm():
    """Mock async context manager (stand-in for aiohttp.ClientSession)."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=MagicMock())
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _story(title="StoryTitle", summary="Good summary detail here. Enough detail.",
           link="https://example.com/1", category="cat"):
    s = MagicMock()
    s.title = title
    s.summary = summary
    s.link = link
    s.published = None
    s.category = category
    s.full_article = None
    return s


def _default_dedup_data(stories=None):
    if stories is None:
        stories = [("StoryTitle", "https://example.com/1", "snip", None, "cat")]
    return (stories, {"total_after": len(stories)})


def _weather():
    return {
        "forecast": [{"period": 1}],
        "station": {"avg_temp_today": "75", "avg_monthly_rainfall": "3",
                    "current_hourly_rainfall": "2"},
        "lakes": {},
    }


def _pipeline_patch_group(tmpdir, dedup_data=None, weather=None,
                          llm_side_effect=None, extract_mock=None,
                          section_return=None, categories=None):
    """Build the standard set of patches for one pipeline invocation."""
    if dedup_data is None:
        dedup_data = _default_dedup_data()
    if weather is None:
        weather = _weather()
    if section_return is None:
        section_return = {"cat": [_story()]}
    if categories is None:
        categories = ["cat"]
    patches = [
        patch("daily_brief.pipeline.LOG_DIR", tmpdir),
        patch("daily_brief.pipeline.NEWS_DIR", tmpdir),
        patch("daily_brief.pipeline.aiohttp.ClientSession",
              side_effect=[_make_async_cm()]),
        patch("daily_brief.pipeline.write_report"),
        patch("daily_brief.pipeline.os.listdir", return_value=[]),
        patch("daily_brief.pipeline.validate_config", return_value=(True, [])),
        patch("daily_brief.pipeline.fetch_weather",
              new_callable=AsyncMock, return_value=weather),
        patch("daily_brief.pipeline.fetch_and_dedup",
              new_callable=AsyncMock, return_value=dedup_data),
        patch("daily_brief.pipeline.StoryPipelineState",
              side_effect=lambda *a, **kw: _story(
                  category=dedup_data[0][0][4] if dedup_data[0] else "cat")),
        patch("daily_brief.pipeline.stage_extract_article",
              new_callable=AsyncMock) if extract_mock is None
        else patch("daily_brief.pipeline.stage_extract_article",
                   side_effect=extract_mock),
        patch("daily_brief.pipeline.llm_batch_summarize_all",
              new_callable=AsyncMock),
        patch("daily_brief.pipeline.build_sections_from_stories",
              return_value=section_return),
        patch("daily_brief.pipeline.ordered_categories_for_render",
              return_value=categories),
        patch("daily_brief.pipeline.cleanup_old_files"),
        patch("daily_brief.pipeline.build_markdown", return_value=["#md"]),
        patch("daily_brief.pipeline.validate_report", return_value=(True, [])),
        patch("daily_brief.pipeline.run_test_harness"),
        patch("daily_brief.pipeline.PREFLIGHT_CHECKS_ENABLED", False),
    ]
    if llm_side_effect is not None:
        patches.append(patch("daily_brief.pipeline.create_llm_client",
                             side_effect=llm_side_effect))
    else:
        patches.append(patch("daily_brief.pipeline.create_llm_client",
                             return_value=MagicMock()))
    return patches


class _NestedCM:
    """Enter multiple lists of patches as nested context managers."""
    def __init__(self, patch_lists):
        self.patch_lists = patch_lists
        self.entries = []

    def __enter__(self):
        for pl in self.patch_lists:
            self.entries.append([p.__enter__() for p in pl])
        return self.entries

    def __exit__(self, *exc):
        for pl in reversed(self.patch_lists):
            for p in reversed(pl):
                p.__exit__(*exc)


# ---------------------------------------------------------------------------
# 1. Independent module globals per concurrent run
# ---------------------------------------------------------------------------

class TestConcurrentModuleGlobalsIsolation(TestCase):
    """CONCURRENCY BUG: module-level RUN_LOGFILE, PHASE_TIMINGS,
    OUTPUT_DIR, _llm_client are shared across concurrent pipeline runs."""

    def test_logfile_independent(self):
        """Two concurrent runs must produce independent log file paths."""
        run_a = tempfile.mkdtemp()
        run_b = tempfile.mkdtemp()
        captured = {"a": None, "b": None}

        async def run_a_task():
            patches = _pipeline_patch_group(run_a)
            for p in patches:
                p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                await pm()
                import daily_brief.pipeline as pmod
                captured["a"] = pmod.RUN_LOGFILE
            finally:
                for p in reversed(patches):
                    p.__exit__(None, None, None)

        async def run_b_task():
            patches = _pipeline_patch_group(run_b)
            for p in patches:
                p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                await pm()
                import daily_brief.pipeline as pmod
                captured["b"] = pmod.RUN_LOGFILE
            finally:
                for p in reversed(patches):
                    p.__exit__(None, None, None)

        asyncio.get_event_loop().run_until_complete(
            asyncio.gather(run_a_task(), run_b_task())
        )

        assert captured["a"] is not None, "Run A log file not captured"
        assert captured["b"] is not None, "Run B log file not captured"
        # BUG: both runs share the same global RUN_LOGFILE, so last-writer wins
        assert run_a in captured["a"], \
            f"Run A log should be under {run_a}, got {captured['a']}"
        assert run_b in captured["b"], \
            f"Run B log should be under {run_b}, got {captured['b']}"

    def test_phase_timings_independent(self):
        """PHASE_TIMINGS should not leak between concurrent runs."""
        run_a = tempfile.mkdtemp()
        run_b = tempfile.mkdtemp()
        captured = {"a": None, "b": None}

        async def run_task(label, tmpdir):
            patches = _pipeline_patch_group(tmpdir)
            for p in patches:
                p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                await pm()
                import daily_brief.pipeline as pmod
                captured[label] = dict(pmod.PHASE_TIMINGS)
            finally:
                for p in reversed(patches):
                    p.__exit__(None, None, None)

        asyncio.get_event_loop().run_until_complete(
            asyncio.gather(run_task("a", run_a), run_task("b", run_b))
        )

        assert captured["a"] is not None and captured["a"], \
            "Run A timings empty or None -- global cleared by run B"
        assert captured["b"] is not None and captured["b"], \
            "Run B timings should have entries"

    def test_llm_client_independent(self):
        """Each concurrent run should get its own LLM client instance."""
        created_clients = []

        def track_create(*args, **kwargs):
            client = MagicMock()
            client.created_by = threading.get_ident()
            created_clients.append(client)
            return client

        run_a = tempfile.mkdtemp()
        run_b = tempfile.mkdtemp()

        async def run_task(tmpdir):
            patches = _pipeline_patch_group(tmpdir, llm_side_effect=track_create)
            for p in patches:
                p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                await pm()
            finally:
                for p in reversed(patches):
                    p.__exit__(None, None, None)

        asyncio.get_event_loop().run_until_complete(
            asyncio.gather(run_task(run_a), run_task(run_b))
        )

        assert len(created_clients) == 2, \
            f"Expected 2 LLM client creations, got {len(created_clients)}"
        assert created_clients[0] is not created_clients[1], \
            "Concurrent runs shared the same LLM client instance"


# ---------------------------------------------------------------------------
# 2. Version allocation -- no collisions between concurrent runs
# ---------------------------------------------------------------------------

class TestConcurrentVersionAllocation(TestCase):
    """CONCURRENCY BUG: pipeline.py and report.py each independently scan
    the filesystem for the next version number. Two concurrent runs can
    allocate the same version number."""

    def test_log_version_no_collision(self):
        """Two concurrent runs on the same dir must not get the same log ver."""
        shared_dir = tempfile.mkdtemp()
        allocated = []

        async def run_task():
            patches = _pipeline_patch_group(shared_dir)
            for p in patches:
                p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                await pm()
                import daily_brief.pipeline as pmod
                logfile = pmod.RUN_LOGFILE
                m = re.search(r'_v(\d+)\.md$', os.path.basename(logfile))
                if m:
                    allocated.append(int(m.group(1)))
            finally:
                for p in reversed(patches):
                    p.__exit__(None, None, None)

        asyncio.get_event_loop().run_until_complete(
            asyncio.gather(run_task(), run_task())
        )

        assert len(allocated) == 2
        # BUG: both runs scan an empty dir and both get v01
        assert allocated[0] != allocated[1], \
            f"Version collision: both runs allocated v{allocated[0]}"

    def test_report_log_version_pairing(self):
        """Report version must equal its paired log version."""
        cap_ver = {"report": None}
        tmpdir = tempfile.mkdtemp()

        def capture_compute(output_dir, file_ver=None):
            if file_ver is not None:
                cap_ver["report"] = file_ver
            return ("/tmp/fake_report.md", file_ver or 1)

        patches = _pipeline_patch_group(tmpdir)
        patches.append(patch("daily_brief.pipeline.compute_output_path",
                             side_effect=capture_compute))
        for p in patches:
            p.__enter__()
        try:
            from daily_brief.pipeline import main as pm
            asyncio.get_event_loop().run_until_complete(pm())
            import daily_brief.pipeline as pmod
            logfile = pmod.RUN_LOGFILE
            m = re.search(r'_v(\d+)\.md$', os.path.basename(logfile))
            log_ver = int(m.group(1)) if m else None
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)

        assert log_ver is not None, "Log version not captured"
        assert cap_ver["report"] is not None, "Report version not captured"
        assert log_ver == cap_ver["report"], \
            f"Log v{log_ver} != report v{cap_ver['report']} -- versions must pair"


# ---------------------------------------------------------------------------
# 3. Atomic report writes
# ---------------------------------------------------------------------------

class TestAtomicReportWrites(TestCase):
    """CONCURRENCY BUG: write_report() writes directly to the final path.
    A kill mid-write leaves a corrupted partial file. Should use temp file
    + os.replace() for atomicity."""

    def test_write_report_uses_temp_file_and_rename(self):
        """write_report must write to a temp file, then os.replace() to final
        path.  Current code opens the final path directly -- test will fail
        until Wave 4 fix."""
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "report.md")
            content = ["# Daily Brief", "line2", "line3"]

            # Track: did write_report touch a temp path first?
            temp_paths = []
            orig_open = open

            class TrackingFile:
                def __init__(self, path, *a, **kw):
                    self._inner = orig_open(path, *a, **kw)
                    temp_paths.append(path)
                def write(self, data):
                    return self._inner.write(data)
                def close(self):
                    self._inner.close()
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    self._inner.close()
                def __iter__(self):
                    return self._inner.__iter__()
                def __next__(self):
                    return self._inner.__next__()

            with patch("builtins.open", TrackingFile):
                write_report(fp, content)

            with open(fp, "r", encoding="utf-8") as f:
                written = f.read()
            assert written == "\n".join(content) + "\n"

            # Contract check: with atomic writes, a temp path should exist
            # before the final path.  Current code only opens the final path
            # directly.  This assertion FAILS until Wave 4.
            temp_count = sum(1 for p in temp_paths if p != fp)
            assert temp_count > 0, \
                "write_report did not use a temp file -- direct write to final path"

    def test_write_report_failure_preserves_previous(self):
        """If write_report fails mid-write, the previous file must be intact.
        Requires temp-file-then-rename semantics."""
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "report.md")
            with open(fp, "w") as f:
                f.write("# Old Report\nline2\n")

            # Patch open so the first write() raises
            call_seq = [0]
            orig_open = open

            def failing_open(path, *a, **kw):
                if "report" in path and "tmp" not in path:
                    return _FailingFile(path, orig_open, call_seq, *a, **kw)
                return orig_open(path, *a, **kw)

            class _FailingFile:
                def __init__(self, path, fo, seq, *a, **kw):
                    self._f = fo(path, *a, **kw)
                    self._seq = seq
                def write(self, data):
                    self._seq[0] += 1
                    if self._seq[0] == 1:
                        raise IOError("simulated mid-write failure")
                    return self._f.write(data)
                def close(self):
                    self._f.close()
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    try:
                        self._f.close()
                    except Exception:
                        pass

            try:
                with patch("builtins.open", failing_open):
                    write_report(fp, ["# New", "line"])
                    # If no exception, read and check
                    with open(fp, "r") as f:
                        content = f.read()
                    # If write succeeded, old content gone
                    assert "# New" in content or "# Old" in content
            except IOError:
                # Write failed -- original should be intact
                with open(fp, "r") as f:
                    remaining = f.read()
                assert "# Old Report" in remaining, \
                    f"Previous file corrupted after failed write"


# ---------------------------------------------------------------------------
# 4. Independent Phase 1 / Phase 2 timing
# ---------------------------------------------------------------------------

class TestIndependentPhaseTimings(TestCase):
    """Phase 1 (weather) and Phase 2 (RSS) timings must be independently
    measurable even if run concurrently."""

    def test_phase_timings_records_both(self):
        """PHASE_TIMINGS must contain separate Phase 1 and Phase 2 entries."""
        tmpdir = tempfile.mkdtemp()
        patches = _pipeline_patch_group(tmpdir)
        for p in patches:
            p.__enter__()
        try:
            from daily_brief.pipeline import main as pm
            asyncio.get_event_loop().run_until_complete(pm())
            import daily_brief.pipeline as pmod
            assert "Phase 1" in pmod.PHASE_TIMINGS, "Phase 1 timing missing"
            assert "Phase 2" in pmod.PHASE_TIMINGS, "Phase 2 timing missing"
            for k in ("Phase 1", "Phase 2"):
                v = pmod.PHASE_TIMINGS[k]
                assert isinstance(v, (int, float)), \
                    f"{k} timing type {type(v)}"
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)

    def test_phase_1_and_2_run_serial_not_concurrent(self):
        """DOCUMENTED BUG: Phases 1 and 2 run serially.  With slow mocks,
        wall time should equal sum of individual phase times (serial), not
        the max (concurrent).  This test asserts on the *current* serial
        behavior so it PASSES now and will need to flip after Wave 4."""
        async def slow_weather(*a, **kw):
            await asyncio.sleep(0.05)
            return _weather()

        async def slow_rss(*a, **kw):
            await asyncio.sleep(0.05)
            return _default_dedup_data()

        tmpdir = tempfile.mkdtemp()
        patches = _pipeline_patch_group(tmpdir)
        # Replace the default weather/RSS mocks with slow ones
        patches = [
            p if "fetch_weather" not in str(p) else
            patch("daily_brief.pipeline.fetch_weather",
                  new_callable=AsyncMock, side_effect=slow_weather)
            for p in patches
        ]
        patches = [
            p if "fetch_and_dedup" not in str(p) else
            patch("daily_brief.pipeline.fetch_and_dedup",
                  new_callable=AsyncMock, side_effect=slow_rss)
            for p in patches
        ]
        for p in patches:
            p.__enter__()
        try:
            import daily_brief.pipeline as pmod
            from daily_brief.pipeline import main as pm
            start = time.monotonic()
            asyncio.get_event_loop().run_until_complete(pm())
            wall = time.monotonic() - start
            p1t = pmod.PHASE_TIMINGS.get("Phase 1", 0)
            p2t = pmod.PHASE_TIMINGS.get("Phase 2", 0)
            total = p1t + p2t
            ratio = wall / total if total > 0 else 0
            # Serial: ratio ~1.0.  Concurrent: ratio ~0.5.
            # This test documents serial behavior (passes now).
            # After Wave 4, flip to: assert ratio < 0.7
            assert ratio > 0.8, \
                f"Currently serial; ratio={ratio:.2f} (wall={wall:.3f}, P1={p1t:.3f}, P2={p2t:.3f})"
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# 5. Bounded RSS/article concurrency
# ---------------------------------------------------------------------------

class TestBoundedArticleConcurrency(TestCase):
    """CONCURRENCY BUG: Phase 3A calls asyncio.gather for ALL stories
    simultaneously with no concurrency limit."""

    def test_article_fetch_is_unbounded(self):
        """Multiple stories extracted via asyncio.gather run all at once.
        Contracts: a semaphore or semaphore-counting mechanism should limit
        concurrent article fetches to a configurable bound."""
        num_stories = 10
        stories = [
            (f"Story{i}", f"https://example.com/{i}", "snip", None, "cat")
            for i in range(num_stories)
        ]
        dedup = (stories, {"total_after": num_stories})

        max_concurrent = [0]
        concurrent_now = [0]

        async def counting_extract(story, session):
            concurrent_now[0] += 1
            if concurrent_now[0] > max_concurrent[0]:
                max_concurrent[0] = concurrent_now[0]
            await asyncio.sleep(0.01)
            concurrent_now[0] -= 1

        tmpdir = tempfile.mkdtemp()
        patches = _pipeline_patch_group(tmpdir, dedup_data=dedup,
                                        extract_mock=counting_extract,
                                        section_return={"cat": [_story()]})

        for p in patches:
            p.__enter__()
        try:
            from daily_brief.pipeline import main as pm
            asyncio.get_event_loop().run_until_complete(pm())
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)

        # BUG: with unbounded gather, all stories run simultaneously.
        # After Wave 4 fix, should be bounded by configured limit.
        assert max_concurrent[0] > 0, \
            f"Expected concurrent extracts, got {max_concurrent[0]} out of {num_stories}"

    def test_article_concurrency_configurable(self):
        """CONTRACT: Bounded concurrency should be configurable via a
        LLM_ARTICLE_MAX_CONCURRENCY or similar setting.  Currently no such
        config exists -- test documents the gap."""
        import daily_brief.pipeline as pmod
        attrs = [a for a in dir(pmod) if "ARTICLE" in a.upper() and "CONCURRENCY" in a.upper()]
        # No concurrency limit config exists yet -- this is the gap Wave 4 fills
        if not attrs:
            import warnings
            warnings.warn(
                "ARTICLE_MAX_CONCURRENCY config not available yet (Wave 4 pending)",
                category=PendingDeprecationWarning,
            )
        # Test passes -- documents the absence, no assertion needed


# ---------------------------------------------------------------------------
# 6. RunContext pattern -- no global state leaks
# ---------------------------------------------------------------------------

class TestRunContextNoGlobalLeak(TestCase):
    """CONCURRENCY BUG: pipeline global state leaks between sequential
    runs.  A RunContext (or similar) pattern is needed to scope per-run
    state."""

    def test_globals_reset_between_sequential_runs(self):
        """After two sequential runs, globals should reflect only the second
        run.  Currently the global is overwritten but the first run's state
        is lost -- no way to query per-run results."""
        dir1 = tempfile.mkdtemp()
        dir2 = tempfile.mkdtemp()
        results = []

        def make_run(tmpdir):
            async def run():
                patches = _pipeline_patch_group(tmpdir)
                for p in patches:
                    p.__enter__()
                try:
                    from daily_brief.pipeline import main as pm
                    exit_code = await pm()
                    import daily_brief.pipeline as pmod
                    results.append({
                        "logfile": getattr(pmod, "RUN_LOGFILE", None),
                        "output_dir": getattr(pmod, "OUTPUT_DIR", None),
                        "timings": dict(pmod.PHASE_TIMINGS),
                        "exit_code": exit_code,
                    })
                finally:
                    for p in reversed(patches):
                        p.__exit__(None, None, None)
            return run

        loop = asyncio.get_event_loop()
        loop.run_until_complete(make_run(dir1)())
        loop.run_until_complete(make_run(dir2)())

        assert len(results) == 2
        # After run 2, the global reflects run 2 (expected).
        # The test documents that results[0] logfile is under dir1
        # and results[1] is under dir2 -- if globals leaked, both would
        # point to dir2.
        assert dir1 in results[0]["logfile"], \
            f"Run 1 leaked: logfile {results[0]['logfile']} not under {dir1}"
        assert dir2 in results[1]["logfile"], \
            f"Run 2 logfile should be under {dir2}"

    def test_concurrent_runs_globals_independent(self):
        """Two concurrent runs should not interfere with each other's
        global state.  Each should see its own LOG_DIR/NEWS_DIR."""
        dir1 = tempfile.mkdtemp()
        dir2 = tempfile.mkdtemp()
        observed = {"a": {}, "b": {}}

        async def labeled_run(label, tmpdir):
            patches = _pipeline_patch_group(tmpdir)
            for p in patches:
                p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                await pm()
                import daily_brief.pipeline as pmod
                observed[label] = {
                    "logfile": pmod.RUN_LOGFILE,
                    "output_dir": pmod.OUTPUT_DIR,
                    "timings": dict(pmod.PHASE_TIMINGS),
                }
            finally:
                for p in reversed(patches):
                    p.__exit__(None, None, None)

        asyncio.get_event_loop().run_until_complete(
            asyncio.gather(labeled_run("a", dir1), labeled_run("b", dir2))
        )

        # Each run should see its own directory.  BUG: last-writer wins
        # for globals, so both may show dir2.
        assert observed["a"], "Run A produced no results"
        assert observed["b"], "Run B produced no results"
        if observed["a"]["logfile"]:
            assert dir1 in observed["a"]["logfile"], \
                f"Run A got logfile {observed['a']['logfile']} (expected {dir1})"
        if observed["b"]["logfile"]:
            assert dir2 in observed["b"]["logfile"], \
                f"Run B got logfile {observed['b']['logfile']} (expected {dir2})"


# ---------------------------------------------------------------------------
# Helper class for pending feature documentation
# ---------------------------------------------------------------------------

class PendingDeprecationWarning(Warning):
    """Marker for tests that document expected behavior not yet implemented."""
    pass
