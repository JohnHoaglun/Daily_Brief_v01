import os
import tempfile
import unittest
from unittest import mock

from daily_brief.rendering.cleanup import cleanup_old_files

# ---------------------------------------------------------------------------
# Pipeline write-order regression
# ---------------------------------------------------------------------------

class TestPipelineWriteOrder(unittest.TestCase):
    """Verify the fix: cleanup runs AFTER write_report, not before.

    Previously (pre-v1.0.119), the order was:
        1. compute_output_path
        2. cleanup_old_files  ← new report NOT on disk yet
        3. write_report       ← adds N+1th file after cleanup
    So if 6 existing reports existed, cleanup reduced to 5,
    then write_report added a 6th — leaving 6 news files.

    After the fix:
        1. compute_output_path
        2. write_report        ← new report IS on disk
        3. cleanup_old_files   ← sees N+1 files, reduces to N
    Leaving exactly `max_log_versions` files.
    """

    def test_cleanup_after_write_yields_correct_count(self):
        """Simulate the fixed order: write first, then cleanup — final count is limit."""
        with tempfile.TemporaryDirectory() as output_dir:
            with tempfile.TemporaryDirectory() as log_dir:
                # 5 existing reports (mtime 1..5)
                for i in range(1, 6):
                    path = os.path.join(output_dir, f"DailyBrief-2026-08-0{i}_v01.md")
                    with open(path, "w") as f:
                        f.write(f"report {i}\n")
                    os.utime(path, (float(i), float(i)))

                existing = sorted(
                    f for f in os.listdir(output_dir)
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
                    f for f in os.listdir(output_dir)
                    if f.startswith("DailyBrief-") and f.endswith(".md")
                )
                self.assertEqual(len(remaining), 5,
                    f"Expected 5, got {len(remaining)}: {remaining}")
                # The oldest should be gone
                self.assertNotIn("DailyBrief-2026-08-01_v01.md", remaining)
                # The newest should survive
                self.assertIn("DailyBrief-2026-08-06_v01.md", remaining)

    def test_old_order_would_have_left_six(self):
        """Demonstrate the old (broken) order: cleanup before write leaves 6 files.

        This test simulates the old behavior explicitly to document the bug.
        """
        with tempfile.TemporaryDirectory() as output_dir:
            with tempfile.TemporaryDirectory() as log_dir:
                # 5 existing reports
                for i in range(1, 6):
                    path = os.path.join(output_dir, f"DailyBrief-2026-08-0{i}_v01.md")
                    with open(path, "w") as f:
                        f.write(f"report {i}\n")
                    os.utime(path, (float(i), float(i)))

                # OLD order: cleanup BEFORE write
                cleanup_old_files(output_dir, log_dir, max_log_versions=5)
                after_cleanup = sorted(
                    f for f in os.listdir(output_dir)
                    if f.startswith("DailyBrief-") and f.endswith(".md")
                )
                self.assertEqual(len(after_cleanup), 5)

                # Then write the new report
                new_path = os.path.join(output_dir, "DailyBrief-2026-08-06_v01.md")
                with open(new_path, "w") as f:
                    f.write("new report\n")

                remaining = sorted(
                    f for f in os.listdir(output_dir)
                    if f.startswith("DailyBrief-") and f.endswith(".md")
                )
                # Old order leaves 6 files — this IS the bug
                self.assertEqual(len(remaining), 6)
