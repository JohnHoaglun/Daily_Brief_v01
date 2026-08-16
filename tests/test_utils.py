"""Tier 1 unit tests for daily_brief/utils.py."""

from types import SimpleNamespace
from unittest import TestCase

from daily_brief.utils import (
    _clean_number,
    _coerce_percent,
    _coerce_temperature_f,
    _count_sentences,
    _extract_first_match,
    _present_weather_value,
    _safe_sentence_summary,
    _safe_text,
    build_context,
    extract_significant_words,
    is_obituary_title,
    is_realt_estate_title,
    strip_html,
)


class TestUtils(TestCase):
    def test___safe_text(self):
        s = _safe_text
        self.assertEqual(s(None), "N/A")
        self.assertEqual(s(""), "N/A")
        self.assertEqual(s("  "), "N/A")
        self.assertEqual(s(None, fallback="—"), "—")
        self.assertEqual(s("  hello  "), "hello")
        self.assertEqual(s(42), "42")
        self.assertEqual(s(3.14), "3.14")
        self.assertEqual(s(True), "True")
        self.assertEqual(s("a" * 5000), "a" * 5000)

    def test_strip_html(self):
        f = strip_html
        self.assertEqual(f("<p>Hello</p>"), "Hello")
        self.assertEqual(f("<b>B</b> and <i>I</i>"), "B and I")
        self.assertEqual(f("<div><span>Deep</span></div>"), "Deep")
        self.assertEqual(f("Plain"), "Plain")
        self.assertEqual(f(""), "")
        self.assertEqual(f("   <b>X</b>   "), "X")
        self.assertEqual(f("Before <t>m</t> after"), "Before m after")

    def test___present_weather_value(self):
        f = _present_weather_value
        for v in (None, "", "  ", "None", "N/A", "NA", "none"):
            self.assertEqual(f(v), "Unavailable")
        self.assertEqual(f(None, fallback="nope"), "nope")
        self.assertEqual(f("Patchy rain possible"), "Patchy rain possible")
        self.assertEqual(f("Dynamic"), "Dynamic")
        self.assertEqual(f(42), "42")

    def test___clean_number(self):
        f = _clean_number
        self.assertEqual(f("72.5\u00b0F"), "72.5")
        self.assertEqual(f("72\u00b0F"), "72")
        self.assertEqual(f("Temp: -3.2\u00b0C"), "-3.2")
        self.assertEqual(f("-10"), "-10")
        self.assertEqual(f("100"), "100")
        self.assertEqual(f("3.14159"), "3.14159")
        self.assertEqual(f("0"), "0")
        self.assertEqual(f("Wind 15 mph gusts 25"), "15")
        self.assertEqual(f("Humidity 85%"), "85")
        for v in ("N/A", "", None, "no number"):
            self.assertEqual(f(v), "0")
        self.assertEqual(f("invalid", fallback="-"), "-")

    def test___safe_sentence_summary(self):
        f = _safe_sentence_summary
        self.assertEqual(f(""), "")
        self.assertEqual(f("One."), "One.")
        self.assertEqual(f("A. B. C."), "A. B. C.")
        self.assertEqual(f("First. Second. Third. Fourth."), "First. Second. Third.")
        self.assertEqual(f("A. B. C. D. E. F. G. H. I. J."), "A. B. C.")
        self.assertEqual(f("  Trimmed.   Two.  "), "Trimmed. Two.")
        self.assertEqual(f("Hello.. World."), "Hello. World.")

    def test___count_sentences(self):
        f = _count_sentences
        self.assertEqual(f(""), 0)
        self.assertEqual(f("Hello."), 1)
        self.assertEqual(f("A. B. C."), 3)
        self.assertEqual(f("Wow! Yes? No."), 3)
        self.assertEqual(f("No punctuation"), 1)
        self.assertEqual(f("  Trimmed.  End.  "), 2)

    def test___coerce_percent(self):
        f = _coerce_percent
        self.assertEqual(f("85%"), "85.0%")
        self.assertEqual(f("85"), "85.0%")
        self.assertEqual(f("3.5%"), "3.5%")
        self.assertEqual(f("3.5"), "3.5%")
        self.assertEqual(f("0%"), "0.0%")
        self.assertEqual(f("100%"), "100.0%")
        self.assertEqual(f("99.9"), "99.9%")
        self.assertIsNone(f(None))
        self.assertIsNone(f("invalid"))
        self.assertIsNone(f("abc10"))

    def test___coerce_temperature_f(self):
        f = _coerce_temperature_f
        self.assertEqual(f("72"), 72.0)
        self.assertEqual(f("72.5\u00b0F"), 72.5)
        self.assertEqual(f("72.3"), 72.3)
        self.assertEqual(f("140"), 140.0)
        self.assertIsNone(f(None))
        self.assertIsNone(f(""))
        self.assertIsNone(f("not a number"))
        self.assertIsNone(f("200"))
        self.assertIsNone(f("141"))

    def test___extract_first_match(self):
        f = _extract_first_match
        self.assertEqual(f("Temp is 72 deg", [r"is (\d+)"]), "72")
        self.assertEqual(f("Temp: 72, Wind: 15", [r"Temp: (\d+)", r"Wind: (\d+)"]), "72")
        self.assertEqual(f("TEMP 72", [r"temp (\d+)"]), "72")
        self.assertIsNone(f("no digits", [r"(\d+)"]))
        self.assertIsNone(f("", [r"(\d+)"]))

    def test_is_obituary_title(self):
        f = is_obituary_title
        for t in (
            "John's Obituary",
            "She Passed Away",
            "Death Notice: Smith",
            "Funeral Services for Jane",
            "Memorial Service for Bob",
        ):
            self.assertTrue(f(t), t)
        for t in ("Local News Update", "", "Weather Report"):
            self.assertFalse(f(t), t)

    def test_is_real_estate_title(self):
        f = is_realt_estate_title
        for t in (
            "Zillow listing",
            "House for sale",
            "Home for rent",
            "New Property",
            "$500k deal",
            "Realtor update",
            "Redfin search",
            "Listing expires",
        ):
            self.assertTrue(f(t), t)
        self.assertFalse(f("Local news"))
        self.assertFalse(f(""))

    def test_build_context(self):
        b = SimpleNamespace
        # Long context (>=50 chars) used directly, truncated to preview_chars
        s = b(context="A" * 800, snippet="s", title="t", category="c")
        self.assertEqual(build_context(s, 600), "A" * 600)
        # Short context falls through to snippet/title
        s = b(context="short", snippet="snippet text", title="The Title", category="news")
        result = build_context(s)
        self.assertIn("snippet text", result)
        self.assertIn("The Title", result)
        self.assertIn("Category: news", result)
        # No snippet, title-only
        s = b(context=None, snippet=None, title="The Title", category="news")
        self.assertIn("The Title", build_context(s))
        # Full fallback
        s = b(context=None, snippet=None, title="", category="news")
        self.assertEqual(build_context(s), "news: ")


class TestExtractSignificantWords(TestCase):
    def test_basic(self):
        f = extract_significant_words
        self.assertEqual(f("Hello world"), ["hello", "world"])
        self.assertEqual(f("Houston's a city"), ["houston", "city"])
        self.assertEqual(f("A B C D E"), [])

    def test_min_len(self):
        f = extract_significant_words
        self.assertEqual(f("Hello world now", min_len=4), ["hello", "world"])
        self.assertEqual(f("Hello world now", min_len=3), ["hello", "world", "now"])

    def test_empty_inputs(self):
        f = extract_significant_words
        self.assertEqual(f(""), [])
        self.assertEqual(f("  "), [])
        self.assertEqual(f(None), [])

    def test_apostrophes(self):
        f = extract_significant_words
        result = f("it's Houston's city", allow_apostrophes=True)
        self.assertIn("it's", result)
        self.assertIn("houston's", result)
        self.assertIn("city", result)

    def test_no_apostrophes(self):
        f = extract_significant_words
        result = f("it's Houston's city", allow_apostrophes=False)
        self.assertEqual(result, ["houston", "city"])
        self.assertNotIn("it", result)
        self.assertNotIn("s", result)

    def test_symbols_ignored(self):
        f = extract_significant_words
        self.assertEqual(f("2026 update", min_len=4), ["update"])
        self.assertEqual(f("---!!!"), [])
        self.assertEqual(f("Weather & News"), ["weather", "news"])

    def test_duplicate_preservation(self):
        f = extract_significant_words
        result = f("the the the tests", min_len=3)
        self.assertEqual(result, ["the", "the", "the", "tests"])
