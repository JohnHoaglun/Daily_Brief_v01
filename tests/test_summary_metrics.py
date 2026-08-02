"""Unit tests for src/daily_brief/llm/summary_metrics.py."""
import os
import sys
from unittest import TestCase

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

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

    def test_slots_defined(self):
        expected = {
            "total_stories", "sub_batches", "batch_calls", "batch_retries",
            "batch_failures", "individual_recovery_attempts", "individual_recovered",
            "auto_fallbacks", "unavailable_summaries", "final_valid", "final_invalid",
            "elapsed_s",
        }
        self.assertEqual(set(SummaryMetrics.__slots__), expected)

    def test_no_extra_attributes(self):
        m = SummaryMetrics()
        with self.assertRaises(AttributeError):
            m.extra_field = "bad"


class TestSummaryMetricsIsValid(TestCase):
    def test_all_valid(self):
        self.assertTrue(SummaryMetrics(total_stories=10, final_valid=10).is_valid)

    def test_mix_valid_fallback(self):
        self.assertTrue(SummaryMetrics(total_stories=10, final_valid=7, auto_fallbacks=3).is_valid)

    def test_with_unavailable(self):
        self.assertTrue(SummaryMetrics(total_stories=10, final_valid=7, auto_fallbacks=2, unavailable_summaries=1).is_valid)

    def test_with_invalid(self):
        self.assertTrue(SummaryMetrics(total_stories=10, final_valid=8, final_invalid=2).is_valid)

    def test_broken_invariant(self):
        self.assertFalse(SummaryMetrics(total_stories=10, final_valid=5, auto_fallbacks=3).is_valid)


class TestSummaryMetricsToDict(TestCase):
    def test_dict_has_all_keys(self):
        d = SummaryMetrics().to_dict()
        expected = {
            "total_stories", "sub_batches", "batch_calls", "batch_retries",
            "batch_failures", "individual_recovery_attempts", "individual_recovered",
            "auto_fallbacks", "unavailable_summaries", "final_valid", "final_invalid",
            "elapsed_s",
        }
        self.assertEqual(set(d.keys()), expected)

    def test_dict_values_match(self):
        m = SummaryMetrics(total_stories=20, final_valid=15, batch_retries=3)
        d = m.to_dict()
        self.assertEqual(d["total_stories"], 20)
        self.assertEqual(d["final_valid"], 15)
        self.assertEqual(d["batch_retries"], 3)


class TestValidateMetrics(TestCase):
    def test_valid_returns_true(self):
        self.assertTrue(validate_metrics(SummaryMetrics(total_stories=5, final_valid=5)))

    def test_invalid_returns_false(self):
        self.assertFalse(validate_metrics(SummaryMetrics(total_stories=5, final_valid=3)))


class TestEmptyMetrics(TestCase):
    def test_total_set_others_zero(self):
        m = empty_metrics(10)
        self.assertEqual(m.total_stories, 10)
        self.assertEqual(m.final_valid, 0)
        self.assertEqual(m.auto_fallbacks, 0)

    def test_empty_zero(self):
        m = empty_metrics(0)
        self.assertEqual(m.total_stories, 0)
        self.assertTrue(m.is_valid)
