"""Unit tests for daily_brief/llm/summary_metrics.py."""
from unittest import TestCase

from daily_brief.llm.summary_metrics import (
    SummaryMetrics,
    validate_metrics,
    empty_metrics,
)


class TestSummaryMetricsConstructor(TestCase):
    def test_default_all_zeros(self):
        m = SummaryMetrics()
        self.assertEqual(m.total_stories, 0)
        self.assertEqual(m.final_valid, 0)
        self.assertEqual(m.auto_fallbacks, 0)
        self.assertEqual(m.elapsed_s, 0.0)

    def test_custom_values(self):
        m = SummaryMetrics(total_stories=10, final_valid=7, auto_fallbacks=3, elapsed_s=42.5)
        self.assertEqual(m.total_stories, 10)
        self.assertEqual(m.final_valid, 7)
        self.assertEqual(m.auto_fallbacks, 3)
        self.assertEqual(m.elapsed_s, 42.5)

class TestSummaryMetricsIsValid(TestCase):
    def test_mixed_valid_fallback_unavailable(self):
        self.assertTrue(SummaryMetrics(total_stories=10, final_valid=7, auto_fallbacks=2, unavailable_summaries=1).is_valid)
        self.assertTrue(SummaryMetrics(total_stories=10, final_valid=8, final_invalid=2).is_valid)
        self.assertFalse(SummaryMetrics(total_stories=10, final_valid=5, auto_fallbacks=3).is_valid)


class TestSummaryMetricsToDict(TestCase):
    def test_dict_keys_and_values(self):
        d = SummaryMetrics().to_dict()
        expected_keys = {
            "total_stories", "sub_batches", "batch_calls", "batch_retries",
            "batch_failures", "individual_recovery_attempts", "individual_recovered",
            "auto_fallbacks", "unavailable_summaries", "final_valid", "final_invalid",
            "elapsed_s",
        }
        self.assertEqual(set(d.keys()), expected_keys)
        m = SummaryMetrics(total_stories=20, final_valid=15, batch_retries=3)
        d = m.to_dict()
        self.assertEqual(d["total_stories"], 20)
        self.assertEqual(d["final_valid"], 15)


class TestValidateAndEmpty(TestCase):
    def test_validate_valid_and_invalid(self):
        self.assertTrue(validate_metrics(SummaryMetrics(total_stories=5, final_valid=5)))
        self.assertFalse(validate_metrics(SummaryMetrics(total_stories=5, final_valid=3)))

    def test_empty_metrics(self):
        m = empty_metrics(10)
        self.assertEqual(m.total_stories, 10)
        self.assertEqual(m.final_valid, 0)
        m0 = empty_metrics(0)
        self.assertEqual(m0.total_stories, 0)
        self.assertTrue(m0.is_valid)
