"""Reduced: newest-retention and empty-dir cleanup."""

import os
import tempfile
from unittest import TestCase

from daily_brief.rendering.cleanup import cleanup_old_files


def _touch(directory: str, filename: str, mtime: float) -> None:
    path = os.path.join(directory, filename)
    with open(path, "w") as f:
        f.write("")
    os.utime(path, (mtime, mtime))


class TestCleanupOldFiles(TestCase):
    def test_retains_max_reports(self):
        """With 6 reports and limit 5, the oldest is removed."""
        with tempfile.TemporaryDirectory() as news_dir:
            with tempfile.TemporaryDirectory() as log_dir:
                for i in range(6):
                    _touch(news_dir, f"DailyBrief-2026-08-0{i + 1}_v01.md", 1000 + i)
                    _touch(log_dir, f"run_log_2026-08-0{i + 1}_v01.md", 1000 + i)

                cleanup_old_files(news_dir, log_dir, 5)

                news_files = sorted(
                    f for f in os.listdir(news_dir)
                    if f.startswith("DailyBrief-") and f.endswith(".md")
                )
                log_files = sorted(
                    f for f in os.listdir(log_dir)
                    if f.startswith("run_log_") and f.endswith(".md")
                )

                self.assertEqual(len(news_files), 5)
                self.assertEqual(len(log_files), 5)
                self.assertNotIn("DailyBrief-2026-08-01_v01.md", news_files)
                self.assertNotIn("run_log_2026-08-01_v01.md", log_files)

    def test_non_matching_files_untouched(self):
        """Files that don't match the prefix pattern are never deleted."""
        with tempfile.TemporaryDirectory() as news_dir:
            _touch(news_dir, "notes.md", 500)
            _touch(news_dir, "DailyBrief-raw.txt", 500)
            cleanup_old_files(news_dir, news_dir, 5)
            self.assertIn("notes.md", os.listdir(news_dir))
            self.assertIn("DailyBrief-raw.txt", os.listdir(news_dir))

    def test_under_limit_no_deletion(self):
        """When fewer files than max, nothing is deleted."""
        with tempfile.TemporaryDirectory() as news_dir:
            for i in range(3):
                _touch(news_dir, f"DailyBrief-2026-08-0{i + 1}_v01.md", 1000 + i)
            cleanup_old_files(news_dir, news_dir, 5)
            news_files = sorted(
                f for f in os.listdir(news_dir)
                if f.startswith("DailyBrief-") and f.endswith(".md")
            )
            self.assertEqual(len(news_files), 3)

    def test_empty_directories_no_error(self):
        """Empty directories don't raise."""
        with tempfile.TemporaryDirectory() as news_dir:
            with tempfile.TemporaryDirectory() as log_dir:
                cleanup_old_files(news_dir, log_dir, 5)


if __name__ == "__main__":
    import unittest
    unittest.main()
