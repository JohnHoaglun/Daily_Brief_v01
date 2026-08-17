"""Tier 1 unit tests for daily_brief/utils.py — compact."""

from types import SimpleNamespace
from unittest import TestCase

from daily_brief.utils import (
    _count_sentences,
    _safe_text,
    extract_significant_words,
    strip_html,
)


class TestUtils(TestCase):
    def test_safe_text(self):
        self.assertEqual(_safe_text(None), "N/A")
        self.assertEqual(_safe_text(""), "N/A")
        self.assertEqual(_safe_text("  "), "N/A")
        self.assertEqual(_safe_text("  hello  "), "hello")
        self.assertEqual(_safe_text(42), "42")

    def test_strip_html(self):
        self.assertEqual(strip_html("<p>Hello</p>"), "Hello")
        self.assertEqual(strip_html("<b>B</b> and <i>I</i>"), "B and I")
        self.assertEqual(strip_html("<div><span>Deep</span></div>"), "Deep")
        self.assertEqual(strip_html("Plain"), "Plain")
        self.assertEqual(strip_html("<t>m</t>"), "m")

    def test_count_sentences(self):
        self.assertEqual(_count_sentences(""), 0)
        self.assertEqual(_count_sentences("Hello."), 1)
        self.assertEqual(_count_sentences("A. B. C."), 3)
        self.assertEqual(_count_sentences("Wow! Yes? No."), 3)
        self.assertEqual(_count_sentences("No punctuation"), 1)

    def test_significant_words(self):
        self.assertEqual(extract_significant_words("Hello world"), ["hello", "world"])
        self.assertEqual(extract_significant_words(""), [])
        self.assertEqual(extract_significant_words(None), [])
        self.assertEqual(extract_significant_words("Hello world", min_len=4), ["hello", "world"])
        self.assertEqual(extract_significant_words("2026 update", min_len=4), ["update"])
        self.assertEqual(extract_significant_words("it's Houston's city", allow_apostrophes=True), ["it's", "houston's", "city"])
