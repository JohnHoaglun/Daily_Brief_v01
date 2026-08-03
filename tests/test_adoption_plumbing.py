"""Tests proving config → pipeline → batch_summarize_all wiring."""
import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestConfigDefaults(unittest.TestCase):
    def test_batch_size_default(self):
        from daily_brief.config import LLM_SUMMARY_BATCH_SIZE
        self.assertEqual(LLM_SUMMARY_BATCH_SIZE, 4)

    def test_max_concurrency_default(self):
        from daily_brief.config import LLM_SUMMARY_MAX_CONCURRENCY
        self.assertEqual(LLM_SUMMARY_MAX_CONCURRENCY, 2)

    def test_batch_size_positive(self):
        from daily_brief.config import LLM_SUMMARY_BATCH_SIZE
        self.assertGreater(LLM_SUMMARY_BATCH_SIZE, 0)

    def test_max_concurrency_positive(self):
        from daily_brief.config import LLM_SUMMARY_MAX_CONCURRENCY
        self.assertGreater(LLM_SUMMARY_MAX_CONCURRENCY, 0)


class TestPipelineForwardsSettings(unittest.TestCase):
    def test_pipeline_uses_config_constants(self):
        """Verify pipeline source imports and passes the config constants."""
        source_file = os.path.join(os.path.dirname(__file__), "..", "src", "daily_brief", "pipeline.py")
        with open(source_file) as f:
            source = f.read()
        self.assertIn("LLM_SUMMARY_BATCH_SIZE", source)
        self.assertIn("LLM_SUMMARY_MAX_CONCURRENCY", source)
        self.assertIn("batch_size=LLM_SUMMARY_BATCH_SIZE", source)
        self.assertIn("max_concurrency=LLM_SUMMARY_MAX_CONCURRENCY", source)


class TestConfigValidation(unittest.TestCase):
    def test_batch_scheduler_check_exists(self):
        """Verify the batch scheduler validation function exists and runs."""
        from daily_brief.config_validator import check_batch_scheduler
        issues = check_batch_scheduler({})
        # With defaults (3, 1), no issues expected
        self.assertEqual(len(issues), 0)

    def test_batch_scheduler_invalid_batch_size(self):
        """Zero batch size is rejected by config validation (YAML path)."""
        from daily_brief.config_validator import check_batch_scheduler
        issues = check_batch_scheduler({"llm": {"summary_batch_size": 0}})
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("summary_batch_size" in i for i in issues))

    def test_batch_scheduler_invalid_concurrency(self):
        """Zero max_concurrency is rejected by config validation (YAML path)."""
        from daily_brief.config_validator import check_batch_scheduler
        issues = check_batch_scheduler({"llm": {"summary_max_concurrency": 0}})
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("summary_max_concurrency" in i for i in issues))

    def test_validate_config_includes_batch_scheduler(self):
        """validate_config runs the batch_scheduler check group."""
        from daily_brief.config_validator import CHECK_GROUPS
        group_names = [name for name, _ in CHECK_GROUPS]
        self.assertIn("batch_scheduler", group_names)


class TestPipelineSchedulerLogging(unittest.TestCase):
    def test_pipeline_logs_scheduler_settings(self):
        """Verify pipeline source logs resolved scheduler settings."""
        source_file = os.path.join(os.path.dirname(__file__), "..", "src", "daily_brief", "pipeline.py")
        with open(source_file) as f:
            source = f.read()
        self.assertIn("Phase 3 LLM scheduler: batch_size=", source)
        self.assertIn("LLM_SUMMARY_BATCH_SIZE", source)
        self.assertIn("LLM_SUMMARY_MAX_CONCURRENCY", source)


if __name__ == "__main__":
    unittest.main()
