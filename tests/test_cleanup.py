"""
Unit tests for daily_brief/rendering/cleanup.py — retention and ordering.
"""

import os
import tempfile
from unittest import TestCase

from daily_brief.rendering.cleanup import cleanup_old_files


def _touch(directory: str, filename: str, mtime: float) -> None:
    """Create an empty file with a given modification time."""
    path = os.path.join(directory, filename)
    with open(path, "w") as f:
        f.write("")
    os.utime(path, (mtime, mtime))


# ---------------------------------------------------------------------------
# Direct cleanup tests
# ---------------------------------------------------------------------------


class TestCleanupOldFiles(TestCase):
    """Verify cleanup retains exactly `max_log_versions` files per directory."""

    def test_retains_max_reports(self):
        """With 6 reports and limit 5, the oldest (by mtime) is removed."""
        with tempfile.TemporaryDirectory() as news_dir:
            with tempfile.TemporaryDirectory() as log_dir:
                for i in range(6):
                    _touch(news_dir, f"DailyBrief-2026-08-0{i + 1}_v01.md", 1000 + i)
                for i in range(6):
                    _touch(log_dir, f"run_log_2026-08-0{i + 1}_v01.md", 1000 + i)

                cleanup_old_files(news_dir, log_dir, 5)

                news_files = sorted(
                    f
                    for f in os.listdir(news_dir)
                    if f.startswith("DailyBrief-") and f.endswith(".md")
                )
                log_files = sorted(
                    f
                    for f in os.listdir(log_dir)
                    if f.startswith("run_log_") and f.endswith(".md")
                )

                self.assertEqual(len(news_files), 5)
                self.assertEqual(len(log_files), 5)

                # The oldest file should have been removed
                self.assertNotIn("DailyBrief-2026-08-01_v01.md", news_files)
                self.assertNotIn("run_log_2026-08-01_v01.md", log_files)

    def test_newest_survive(self):
        """The newest files (by mtime) are always retained."""
        with tempfile.TemporaryDirectory() as news_dir:
            with tempfile.TemporaryDirectory() as log_dir:
                # Files 1..6, increasing mtime
                for i in range(1, 7):
                    _touch(news_dir, f"DailyBrief-2026-08-0{i}_v01.md", 1000 + i)
                    _touch(log_dir, f"run_log_2026-08-0{i}_v01.md", 1000 + i)

                cleanup_old_files(news_dir, log_dir, 5)

                news_files = sorted(os.listdir(news_dir))
                log_files = sorted(os.listdir(log_dir))

                # Newest should survive
                for i in range(2, 7):
                    self.assertIn(f"DailyBrief-2026-08-0{i}_v01.md", news_files)
                    self.assertIn(f"run_log_2026-08-0{i}_v01.md", log_files)

    def test_non_matching_files_untouched(self):
        """Files that don't match the prefix pattern are never deleted."""
        with tempfile.TemporaryDirectory() as news_dir:
            with tempfile.TemporaryDirectory() as log_dir:
                for i in range(6):
                    _touch(news_dir, f"DailyBrief-2026-08-0{i + 1}_v01.md", 1000 + i)
                    _touch(log_dir, f"run_log_2026-08-0{i + 1}_v01.md", 1000 + i)

                # Non-matching files
                _touch(news_dir, ".DS_Store", 500)
                _touch(news_dir, "notes.md", 500)
                _touch(news_dir, "DailyBrief-raw.txt", 500)
                _touch(log_dir, "general.log", 500)
                _touch(log_dir, "llm_batch_benchmark.json", 500)
                _touch(log_dir, "run_log_notes.txt", 500)

                cleanup_old_files(news_dir, log_dir, 5)

                news_contents = os.listdir(news_dir)
                log_contents = os.listdir(log_dir)

                self.assertIn("notes.md", news_contents)
                self.assertIn("DailyBrief-raw.txt", news_contents)
                self.assertIn("general.log", log_contents)
                self.assertIn("llm_batch_benchmark.json", log_contents)
                self.assertIn("run_log_notes.txt", log_contents)

    def test_under_limit_no_deletion(self):
        """When there are fewer files than max, nothing is deleted."""
        with tempfile.TemporaryDirectory() as news_dir:
            with tempfile.TemporaryDirectory() as log_dir:
                for i in range(3):
                    _touch(news_dir, f"DailyBrief-2026-08-0{i + 1}_v01.md", 1000 + i)
                    _touch(log_dir, f"run_log_2026-08-0{i + 1}_v01.md", 1000 + i)

                cleanup_old_files(news_dir, log_dir, 5)

                news_files = sorted(
                    f
                    for f in os.listdir(news_dir)
                    if f.startswith("DailyBrief-") and f.endswith(".md")
                )
                log_files = sorted(
                    f
                    for f in os.listdir(log_dir)
                    if f.startswith("run_log_") and f.endswith(".md")
                )

                self.assertEqual(len(news_files), 3)
                self.assertEqual(len(log_files), 3)

    def test_empty_directories_no_error(self):
        """Empty directories don't raise."""
        with tempfile.TemporaryDirectory() as news_dir:
            with tempfile.TemporaryDirectory() as log_dir:
                cleanup_old_files(news_dir, log_dir, 5)  # Should not raise
                # No assertions needed, just verify no exception

    def test_cleanup_runs_after_report_write(self):
        """Pipeline regression: write_report runs before cleanup, final count is limit."""
        with tempfile.TemporaryDirectory() as output_dir:
            with tempfile.TemporaryDirectory() as log_dir:
                # 5 existing reports (mtime 1..5)
                for i in range(1, 6):
                    path = os.path.join(output_dir, f"DailyBrief-2026-08-0{i}_v01.md")
                    with open(path, "w") as f:
                        f.write(f"report {i}\n")
                    os.utime(path, (float(i), float(i)))

                existing = sorted(
                    f
                    for f in os.listdir(output_dir)
                    if f.startswith("DailyBrief-") and f.endswith(".md")
                )
                self.assertEqual(len(existing), 5)

                # Simulate write_report creating the 6th (newest, mtime=10)
                new_path = os.path.join(output_dir, "DailyBrief-2026-08-06_v01.md")
                with open(new_path, "w") as f:
                    f.write("new report\n")
                os.utime(new_path, (10.0, 10.0))

                # Now run cleanup (should see 6 files, keep 5, remove oldest)
                cleanup_old_files(output_dir, log_dir, max_log_versions=5)

                remaining = sorted(
                    f
                    for f in os.listdir(output_dir)
                    if f.startswith("DailyBrief-") and f.endswith(".md")
                )
                self.assertEqual(
                    len(remaining), 5, f"Expected 5, got {len(remaining)}: {remaining}"
                )
                self.assertNotIn("DailyBrief-2026-08-01_v01.md", remaining)
                self.assertIn("DailyBrief-2026-08-06_v01.md", remaining)
