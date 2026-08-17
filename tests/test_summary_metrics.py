"""Reduced: metrics creation and one serialization check."""

from unittest import TestCase

from daily_brief.llm.summary_metrics import (
    SummaryMetrics,
    empty_metrics,
    validate_metrics,
)


class TestSummaryMetricsConstructor(TestCase):
    def test_default_all_zeros(self):
        m = SummaryMetrics()
        self.assertEqual(m.total_stories, 0)
        self.assertEqual(m.final_valid, 0)
        self.assertEqual(m.elapsed_s, 0.0)

    def test_custom_values(self):
        m = SummaryMetrics(total_stories=10, final_valid=7, auto_fallbacks=3, elapsed_s=42.5)
        self.assertEqual(m.total_stories, 10)
        self.assertEqual(m.final_valid, 7)


class TestSummaryMetricsToDict(TestCase):
    def test_dict_serialization(self):
        m = SummaryMetrics(total_stories=20, final_valid=15, batch_retries=3)
        d = m.to_dict()
        expected_keys = {
            "total_stories", "sub_batches", "batch_calls", "batch_retries",
            "batch_failures", "individual_recovery_attempts", "individual_recovered",
            "auto_fallbacks", "unavailable_summaries", "final_valid", "final_invalid",
            "elapsed_s",
        }
        self.assertEqual(set(d.keys()), expected_keys)
        self.assertEqual(d["total_stories"], 20)
        self.assertEqual(d["final_valid"], 15)


class TestValidateAndEmpty(TestCase):
    def test_validate_valid(self):
        self.assertTrue(validate_metrics(SummaryMetrics(total_stories=5, final_valid=5)))

    def test_validate_invalid(self):
        self.assertFalse(validate_metrics(SummaryMetrics(total_stories=5, final_valid=3)))

    def test_empty_metrics(self):
        m = empty_metrics(10)
        self.assertEqual(m.total_stories, 10)
        self.assertEqual(m.final_valid, 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
