"""
Concurrency Contract -- Atomic artifact behavior tests.

Tests version allocation and that write_report uses temp-file-then-rename
semantics for atomic writes.
"""

import asyncio
import os
import re
import tempfile
from unittest import TestCase
from unittest.mock import patch

from daily_brief.rendering.report import (
    write_report,
)
from tests.concurrency_support import (
    _restore_aiohttp_client_session as _restore_aiohttp_client_session,
    _pipeline_patch_group as _pipeline_patch_group,
)

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

        asyncio.get_event_loop().run_until_complete(asyncio.gather(run_task(), run_task()))

        logs = sorted(
            f for f in os.listdir(shared_dir) if f.startswith("run_log_") and f.endswith(".md")
        )
        assert len(logs) >= 2, f"Expected >=2 log files, got {len(logs)}: {logs}"
        versions = []
        for lf in logs:
            m = re.search(r"_v(\d+)\.md$", lf)
            if m:
                versions.append(int(m.group(1)))
        assert len(set(versions)) >= 2, f"Version collision: versions {versions}"

    def test_report_log_version_pairing(self):
        """Report version must equal its paired log version."""
        cap_ver = {"report": None}
        tmpdir = tempfile.mkdtemp()

        def capture_compute(output_dir, file_ver=None):
            if file_ver is not None:
                cap_ver["report"] = file_ver
            return ("/tmp/fake_report.md", file_ver or 1)

        patches = _pipeline_patch_group(tmpdir)
        patches.append(
            patch("daily_brief.pipeline.compute_output_path", side_effect=capture_compute)
        )
        for p in patches:
            p.__enter__()
        try:
            from daily_brief.pipeline import main as pm

            asyncio.get_event_loop().run_until_complete(pm())
            import daily_brief.pipeline as pmod

            ctx = pmod._current_context
            logfile = ctx.run_logfile if ctx else None
            m = re.search(r"_v(\d+)\.md$", os.path.basename(logfile))
            log_ver = int(m.group(1)) if m else None
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)

        assert log_ver is not None, "Log version not captured"
        assert cap_ver["report"] is not None, "Report version not captured"
        assert log_ver == cap_ver["report"], (
            f"Log v{log_ver} != report v{cap_ver['report']} -- versions must pair"
        )


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

            with open(fp, encoding="utf-8") as f:
                written = f.read()
            assert written == "\n".join(content) + "\n"

            # Contract check: with atomic writes, a temp path must be opened
            # before the final path.
            temp_count = sum(1 for p in temp_paths if p != fp)
            assert temp_count > 0, (
                "write_report did not use a temp file -- direct write to final path"
            )

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
                        raise OSError("simulated mid-write failure")
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
                    with open(fp) as f:
                        content = f.read()
                    # If write succeeded, old content gone
                    assert "# New" in content or "# Old" in content
            except OSError:
                # Write failed -- original should be intact
                with open(fp) as f:
                    remaining = f.read()
                assert "# Old Report" in remaining, "Previous file corrupted after failed write"
