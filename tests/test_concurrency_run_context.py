"""
Concurrency Contract -- Run-context isolation tests.

Tests that concurrent main() invocations own independent module globals
(phase timings, logfile paths, LLM client instances) via RunContext scoping.
"""

import asyncio
import os
import re
import tempfile
import threading
from unittest import TestCase
from unittest.mock import MagicMock, patch

from tests.concurrency_support import (
    _restore_aiohttp_client_session as _restore_aiohttp_client_session,
    _pipeline_patch_group as _pipeline_patch_group,
)


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

        asyncio.get_event_loop().run_until_complete(asyncio.gather(run_task(0), run_task(1)))

        logs = sorted(
            f for f in os.listdir(shared_dir) if f.startswith("run_log_") and f.endswith(".md")
        )
        assert len(logs) >= 2, f"Expected >=2 log files, got {len(logs)}: {logs}"
        versions = []
        for lf in logs:
            m = re.search(r"_v(\d+)\.md$", lf)
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

        assert captured["a"] is not None and captured["a"], (
            "Run A timings empty or None -- global cleared by run B"
        )
        assert captured["b"] is not None and captured["b"], "Run B timings should have entries"

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

        assert len(created_clients) == 2, (
            f"Expected 2 LLM client creations, got {len(created_clients)}"
        )
        assert created_clients[0] is not created_clients[1], (
            "Concurrent runs shared the same LLM client instance"
        )


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

                    results.append(
                        {
                            "logfile": getattr(pmod, "RUN_LOGFILE", None),
                            "output_dir": getattr(pmod, "OUTPUT_DIR", None),
                            "timings": dict(pmod.PHASE_TIMINGS),
                            "exit_code": exit_code,
                        }
                    )
                finally:
                    for p in reversed(patches):
                        p.__exit__(None, None, None)

            return run

        loop = asyncio.get_event_loop()
        loop.run_until_complete(make_run(dir1)())
        loop.run_until_complete(make_run(dir2)())

        assert len(results) == 2
        assert dir1 in results[0]["logfile"], (
            f"Run 1 logfile {results[0]['logfile']} not under {dir1}"
        )
        assert dir2 in results[1]["logfile"], (
            f"Run 2 logfile {results[1]['logfile']} not under {dir2}"
        )
        # Log files should be distinct versions in their respective dirs
        assert results[0]["logfile"] != results[1]["logfile"], (
            "Sequential runs should produce different log paths"
        )

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

        asyncio.get_event_loop().run_until_complete(asyncio.gather(run_task(), run_task()))

        logs = sorted(
            f for f in os.listdir(shared) if f.startswith("run_log_") and f.endswith(".md")
        )
        assert len(logs) >= 2, f"Expected >=2 log files, got {len(logs)}: {logs}"
        versions = set()
        for lf in logs:
            m = re.search(r"_v(\d+)\.md$", lf)
            if m:
                versions.add(int(m.group(1)))
        assert len(versions) >= 2, f"Expected >=2 distinct versions, got {versions}"
        import daily_brief.pipeline as pmod

        assert pmod.PHASE_TIMINGS, "Pipeline should have recorded phase timings"
        assert "Phase 1" in pmod.PHASE_TIMINGS, "Phase 1 timing missing"
        assert "Phase 2" in pmod.PHASE_TIMINGS, "Phase 2 timing missing"
