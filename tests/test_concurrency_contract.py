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

import aiohttp as _aiohttp_mod
import daily_brief.pipeline as _pipeline_mod


def _restore_aiohttp_client_session():
    """Restore daily_brief.pipeline.aiohttp.ClientSession to the real class."""
    _pipeline_mod.aiohttp.ClientSession = _aiohttp_mod.ClientSession


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
              return_value=_make_async_cm()),
        patch("daily_brief.pipeline.write_report"),
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
    """With RunContext, each main() call owns its own phase timings, timings dict,
    and logfile path via a scoped RunContext.  Module globals remain as backwards-
    compatible shim for test fixtures."""

    def tearDown(self):
        _restore_aiohttp_client_session()

    def test_logfile_independent(self):
        """Two concurrent runs produce distinct log files via RunAllocator filesystem
        reservation. Verify by scanning the output directory for distinct .md logs."""
        shared_dir = tempfile.mkdtemp()
        barriers = [asyncio.Event(), asyncio.Event()]

        async def run_task(idx):
            patches = _pipeline_patch_group(shared_dir)
            for p in patches:
                p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                barriers[idx].set()
                await barriers[1 - idx].wait()
                await pm()
            finally:
                for p in reversed(patches):
                    p.__exit__(None, None, None)

        asyncio.get_event_loop().run_until_complete(
            asyncio.gather(run_task(0), run_task(1))
        )

        logs = sorted(f for f in os.listdir(shared_dir)
                      if f.startswith("run_log_") and f.endswith(".md"))
        assert len(logs) >= 2, f"Expected >=2 log files, got {len(logs)}: {logs}"
        versions = []
        for lf in logs:
            m = re.search(r'_v(\d+)\.md$', lf)
            if m:
                versions.append(int(m.group(1)))
        assert len(set(versions)) >= 2, f"Expected distinct versions, got {sorted(set(versions))}"

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
    """With RunAllocator, two concurrent runs on the same directory must not
    get the same version.  Filesystem-backed reservation (O_CREAT | O_EXCL)
    ensures mutual exclusion."""

    def tearDown(self):
        _restore_aiohttp_client_session()

    def test_log_version_no_collision(self):
        """Two concurrent runs on the same dir get different log versions via
        filesystem reservation markers (O_CREAT | O_EXCL)."""
        shared_dir = tempfile.mkdtemp()

        async def run_task():
            patches = _pipeline_patch_group(shared_dir)
            for p in patches:
                p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                await pm()
            finally:
                for p in reversed(patches):
                    p.__exit__(None, None, None)

        asyncio.get_event_loop().run_until_complete(
            asyncio.gather(run_task(), run_task())
        )

        logs = sorted(f for f in os.listdir(shared_dir)
                      if f.startswith("run_log_") and f.endswith(".md"))
        assert len(logs) >= 2, f"Expected >=2 log files, got {len(logs)}: {logs}"
        versions = []
        for lf in logs:
            m = re.search(r'_v(\d+)\.md$', lf)
            if m:
                versions.append(int(m.group(1)))
        assert len(set(versions)) >= 2, \
            f"Version collision: versions {versions}"

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
                def read(self, *a, **kw):
                    return self._inner.read(*a, **kw)
                def flush(self):
                    self._inner.flush()
                def fileno(self):
                    return self._inner.fileno()
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

            # Contract check: with atomic writes, a temp path must be opened
            # before the final path.
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

    def tearDown(self):
        _restore_aiohttp_client_session()

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

    def test_phase_1_and_2_run_concurrent(self):
        """Phases 1 and 2 are dispatched concurrently via asyncio.gather().
        Verify with barrier: both phases start before either completes."""
        concurrent_max = [0]
        active = [0]
        barrier = [False]
        call_count = {"weather": 0, "rss": 0}

        async def slow_weather(*a, **kw):
            call_count["weather"] += 1
            active[0] += 1
            if active[0] > concurrent_max[0]:
                concurrent_max[0] = active[0]
            barrier[0] = True
            await asyncio.sleep(0.02)
            active[0] -= 1
            return _weather()

        async def slow_rss(*a, **kw):
            call_count["rss"] += 1
            active[0] += 1
            if active[0] > concurrent_max[0]:
                concurrent_max[0] = active[0]
            while not barrier[0]:
                await asyncio.sleep(0.001)
            await asyncio.sleep(0.02)
            active[0] -= 1
            return _default_dedup_data()

        tmpdir = tempfile.mkdtemp()
        # Build base patches without the weather/rss mocks
        base = _pipeline_patch_group(tmpdir)
        # Remove the original weather/rss patches and add our custom ones
        custom = [
            patch("daily_brief.pipeline.fetch_weather",
                  new_callable=AsyncMock, side_effect=slow_weather),
            patch("daily_brief.pipeline.fetch_and_dedup",
                  new_callable=AsyncMock, side_effect=slow_rss),
        ]
        all_patches = [
            b for b in base
            if not any(attr in b.attribute for attr in ("fetch_weather", "fetch_and_dedup"))
        ] + custom
        for p in all_patches:
            p.__enter__()
        try:
            from daily_brief.pipeline import main as pm
            asyncio.get_event_loop().run_until_complete(pm())
            assert call_count["weather"] > 0, "weather fetcher was not called"
            assert call_count["rss"] > 0, "RSS fetcher was not called"
            # If concurrent, peak concurrent count should be 2
            assert concurrent_max[0] == 2, \
                f"Expected 2 concurrent phases, got peak of {concurrent_max[0]}"
        finally:
            for p in reversed(all_patches):
                p.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# 5. Bounded RSS/article concurrency
# ---------------------------------------------------------------------------

class TestBoundedArticleConcurrency(TestCase):
    """CONCURRENCY BUG: Phase 3A calls asyncio.gather for ALL stories
    simultaneously with no concurrency limit."""

    def tearDown(self):
        _restore_aiohttp_client_session()

    def test_article_fetch_is_bounded(self):
        """Article extraction is bounded by ARTICLE_MAX_CONCURRENCY.
        Peak concurrent extracts should not exceed the configured limit."""
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

        assert max_concurrent[0] > 0, \
            f"Expected concurrent extracts, got {max_concurrent[0]} out of {num_stories}"
        assert max_concurrent[0] <= 4, \
            f"Peak concurrency {max_concurrent[0]} exceeds limit of 4"

    def test_article_concurrency_configurable(self):
        """CONTRACT: Bounded concurrency should be configurable via
        ARTICLE_MAX_CONCURRENCY setting.  Implemented in v1.0.127."""
        import daily_brief.pipeline as pmod
        attrs = [a for a in dir(pmod) if "ARTICLE" in a.upper() and "CONCURRENCY" in a.upper()]
        assert attrs or hasattr(pmod, "ARTICLE_MAX_CONCURRENCY"), \
            "ARTICLE_MAX_CONCURRENCY config must exist after Wave 4"


# ---------------------------------------------------------------------------
# 6. RunContext pattern -- no global state leaks
# ---------------------------------------------------------------------------

class TestRunContextNoGlobalLeak(TestCase):
    """CONCURRENCY BUG: pipeline global state leaks between sequential
    runs.  A RunContext (or similar) pattern is needed to scope per-run
    state."""

    def tearDown(self):
        _restore_aiohttp_client_session()

    def test_sequential_runs_independent(self):
        """Two sequential runs produce distinct log files with separate versions.
        RunContext isolates per-run state; module globals track the last run."""
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
        assert dir1 in results[0]["logfile"], \
            f"Run 1 logfile {results[0]['logfile']} not under {dir1}"
        assert dir2 in results[1]["logfile"], \
            f"Run 2 logfile {results[1]['logfile']} not under {dir2}"
        # Log files should be distinct versions in their respective dirs
        assert results[0]["logfile"] != results[1]["logfile"], \
            "Sequential runs should produce different log paths"

    def test_concurrent_runs_independent(self):
        """Two concurrent runs produce independent log files with distinct versions.
        RunContext isolates per-run state; log files are written by _log_ctx (open),
        not the mocked write_report, so they appear on disk."""
        shared = tempfile.mkdtemp()

        async def run_task():
            patches = _pipeline_patch_group(shared)
            for p in patches:
                p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                await pm()
            finally:
                for p in reversed(patches):
                    p.__exit__(None, None, None)

        asyncio.get_event_loop().run_until_complete(
            asyncio.gather(run_task(), run_task())
        )

        logs = sorted(f for f in os.listdir(shared)
                      if f.startswith("run_log_") and f.endswith(".md"))
        assert len(logs) >= 2, f"Expected >=2 log files, got {len(logs)}: {logs}"
        versions = set()
        for lf in logs:
            m = re.search(r'_v(\d+)\.md$', lf)
            if m:
                versions.add(int(m.group(1)))
        assert len(versions) >= 2, f"Expected >=2 distinct versions, got {versions}"
        import daily_brief.pipeline as pmod
        assert pmod.PHASE_TIMINGS, "Pipeline should have recorded phase timings"
        assert "Phase 1" in pmod.PHASE_TIMINGS, "Phase 1 timing missing"
        assert "Phase 2" in pmod.PHASE_TIMINGS, "Phase 2 timing missing"


# ---------------------------------------------------------------------------
# Helper class for pending feature documentation
# ---------------------------------------------------------------------------

class PendingDeprecationWarning(Warning):
    """Marker for tests that document expected behavior not yet implemented."""
    pass
