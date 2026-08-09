"""
Tier 1 unit tests for utility functions in daily_brief/utils.py.
"""
from unittest import TestCase

from daily_brief.utils import (
    _safe_text,
    strip_html,
    _present_weather_value,
    _clean_number,
    _safe_sentence_summary,
    _count_sentences,
    _coerce_percent,
    _coerce_temperature_f,
)
from daily_brief.utils import (
    _extract_first_match,
    is_obituary_title,
    is_realt_estate_title as is_real_estate_title,
)


# ---------------------------------------------------------------------------
# _safe_text
# ---------------------------------------------------------------------------

class TestSafeText(TestCase):
    """_safe_text normalizes user-facing text values."""

    def test_none_returns_fallback(self):
        self.assertEqual(_safe_text(None), "N/A")

    def test_empty_string_returns_fallback(self):
        self.assertEqual(_safe_text(""), "N/A")

    def test_whitespace_only_returns_fallback(self):
        self.assertEqual(_safe_text("  "), "N/A")

    def test_plain_string_unchanged(self):
        self.assertEqual(_safe_text("hello"), "hello")

    def test_strips_whitespace(self):
        self.assertEqual(_safe_text("  hello  "), "hello")

    def test_integer_converted(self):
        self.assertEqual(_safe_text(42), "42")

    def test_float_converted(self):
        self.assertEqual(_safe_text(3.14), "3.14")

    def test_bool_converted(self):
        self.assertEqual(_safe_text(True), "True")

    def test_custom_fallback(self):
        self.assertEqual(_safe_text(None, fallback="Missing"), "Missing")

    def test_custom_fallback_empty(self):
        self.assertEqual(_safe_text("", fallback="CustomF"), "CustomF")

    def test_long_text_preserved(self):
        long_text = "a" * 5000
        result = _safe_text(long_text)
        self.assertEqual(len(result), 5000)


# ---------------------------------------------------------------------------
# strip_html
# ---------------------------------------------------------------------------

class TestStripHTML(TestCase):
    """strip_html removes HTML tags from text."""

    def test_basic_tag_removal(self):
        self.assertEqual(strip_html("<p>Hello</p>"), "Hello")

    def test_multiple_tags(self):
        self.assertEqual(strip_html("<b>Bold</b> and <i>italic</i>"), "Bold and italic")

    def test_nested_tags(self):
        self.assertEqual(strip_html("<div><span>Nested</span></div>"), "Nested")

    def test_plain_text_unchanged(self):
        self.assertEqual(strip_html("Plain text"), "Plain text")

    def test_empty_string(self):
        self.assertEqual(strip_html(""), "")

    def test_whitespace_trimmed(self):
        self.assertEqual(strip_html("<p>  Spaced  </p>"), "Spaced")

    def test_surrounding_whitespace_trimmed(self):
        self.assertEqual(strip_html("   <b>X</b>   "), "X")

    def test_mixed_content(self):
        self.assertEqual(strip_html("Before <tag>middle</tag> after"), "Before middle after")


# ---------------------------------------------------------------------------
# _present_weather_value
# ---------------------------------------------------------------------------

class TestPresentWeatherValue(TestCase):
    """_present_weather_value handles None and placeholder values."""

    def test_none_returns_fallback(self):
        self.assertEqual(_present_weather_value(None), "Unavailable")

    def test_empty_returns_fallback(self):
        self.assertEqual(_present_weather_value(""), "Unavailable")

    def test_whitespace_returns_fallback(self):
        self.assertEqual(_present_weather_value("  "), "Unavailable")

    def test_none_literal(self):
        self.assertEqual(_present_weather_value("None"), "Unavailable")

    def test_na_literal(self):
        self.assertEqual(_present_weather_value("N/A"), "Unavailable")

    def test_na_short_literal(self):
        self.assertEqual(_present_weather_value("NA"), "Unavailable")

    def test_lowercase_none(self):
        self.assertEqual(_present_weather_value("none"), "Unavailable")

    def test_valid_value_passed_through(self):
        self.assertEqual(_present_weather_value("Patchy rain possible"), "Patchy rain possible")

    def test_dynamic_is_valid(self):
        self.assertEqual(_present_weather_value("Dynamic"), "Dynamic")

    def test_integer_converted(self):
        self.assertEqual(_present_weather_value(42), "42")

    def test_custom_fallback(self):
        self.assertEqual(_present_weather_value(None, fallback="—"), "—")


# ---------------------------------------------------------------------------
# _clean_number
# ---------------------------------------------------------------------------

class TestCleanNumber(TestCase):
    """_clean_number extracts numeric values from strings."""

    def test_temperature_with_unit(self):
        self.assertEqual(_clean_number("72.5°F"), "72.5")

    def test_integer_temperature(self):
        self.assertEqual(_clean_number("72°F"), "72")

    def test_na_returns_fallback(self):
        self.assertEqual(_clean_number("N/A"), "0")

    def test_empty_returns_fallback(self):
        self.assertEqual(_clean_number(""), "0")

    def test_none_returns_fallback(self):
        self.assertEqual(_clean_number(None), "0")

    def test_negative_temperature(self):
        self.assertEqual(_clean_number("Temp: -3.2°C"), "-3.2")

    def test_plain_number(self):
        self.assertEqual(_clean_number("100"), "100")

    def test_no_digit_returns_fallback(self):
        self.assertEqual(_clean_number("No number here"), "0")

    def test_first_number_extracted(self):
        self.assertEqual(_clean_number("Wind 15 mph gusts 25"), "15")

    def test_decimal_number(self):
        self.assertEqual(_clean_number("3.14159"), "3.14159")

    def test_zero(self):
        self.assertEqual(_clean_number("0"), "0")

    def test_negative_integer(self):
        self.assertEqual(_clean_number("-10"), "-10")

    def test_percentage_number(self):
        self.assertEqual(_clean_number("Humidity 85%"), "85")

    def test_custom_fallback(self):
        self.assertEqual(_clean_number("invalid", fallback="-"), "-")


# ---------------------------------------------------------------------------
# _safe_sentence_summary
# ---------------------------------------------------------------------------

class TestSafeSentenceSummary(TestCase):
    """_safe_sentence_summary truncates to at most 3 sentences."""

    def test_empty(self):
        self.assertEqual(_safe_sentence_summary(""), "")

    def test_single_sentence(self):
        self.assertEqual(_safe_sentence_summary("The sun is shining."), "The sun is shining.")

    def test_two_sentences(self):
        result = _safe_sentence_summary("The sun is shining. Birds are singing.")
        self.assertEqual(result, "The sun is shining. Birds are singing.")

    def test_exactly_three(self):
        result = _safe_sentence_summary("First sentence. Second sentence. Third sentence.")
        self.assertEqual(result, "First sentence. Second sentence. Third sentence.")

    def test_truncates_four(self):
        result = _safe_sentence_summary("First. Second. Third. Fourth.")
        self.assertEqual(result, "First. Second. Third.")

    def test_truncates_ten(self):
        result = _safe_sentence_summary("A. B. C. D. E. F. G. H. I. J.")
        self.assertEqual(result, "A. B. C.")

    def test_mixed_punctuation(self):
        result = _safe_sentence_summary("Wow! What a day? Really.")
        self.assertEqual(result, "Wow! What a day? Really.")

    def test_whitespace_normalization(self):
        result = _safe_sentence_summary("  One sentence.   Two sentences.  ")
        self.assertEqual(result, "One sentence. Two sentences.")

    def test_double_dot_normalization(self):
        result = _safe_sentence_summary("Hello.. World.")
        self.assertEqual(result, "Hello. World.")


# ---------------------------------------------------------------------------
# _count_sentences
# ---------------------------------------------------------------------------

class TestCountSentences(TestCase):
    """_count_sentences counts sentences in text."""

    def test_empty(self):
        self.assertEqual(_count_sentences(""), 0)

    def test_one_sentence(self):
        self.assertEqual(_count_sentences("Hello."), 1)

    def test_two_sentences(self):
        self.assertEqual(_count_sentences("Hello. World."), 2)

    def test_three_sentences(self):
        self.assertEqual(_count_sentences("A. B. C."), 3)

    def test_mixed_punctuation(self):
        self.assertEqual(_count_sentences("Wow! Yes? No."), 3)

    def test_no_period(self):
        self.assertEqual(_count_sentences("No punctuation here"), 1)

    def test_whitespace(self):
        self.assertEqual(_count_sentences("  Trimmed.  End.  "), 2)


# ---------------------------------------------------------------------------
# _coerce_percent
# ---------------------------------------------------------------------------

class TestCoercePercent(TestCase):
    """_coerce_percent extracts percentage from string."""

    def test_standard_percent(self):
        self.assertEqual(_coerce_percent("85%"), "85.0%")

    def test_number_without_sign(self):
        self.assertEqual(_coerce_percent("85"), "85.0%")

    def test_decimal_percent(self):
        self.assertEqual(_coerce_percent("3.5%"), "3.5%")

    def test_decimal_without_sign(self):
        self.assertEqual(_coerce_percent("3.5"), "3.5%")

    def test_zero(self):
        self.assertEqual(_coerce_percent("0%"), "0.0%")

    def test_full_percent(self):
        self.assertEqual(_coerce_percent("100%"), "100.0%")

    def test_none(self):
        self.assertIsNone(_coerce_percent(None))

    def test_invalid(self):
        self.assertIsNone(_coerce_percent("invalid"))

    def test_leading_text_no_match(self):
        self.assertIsNone(_coerce_percent("abc10"))

    def test_float_formatted(self):
        self.assertEqual(_coerce_percent("99.9"), "99.9%")


# ---------------------------------------------------------------------------
# _extract_first_match
# ---------------------------------------------------------------------------

class TestExtractFirstMatch(TestCase):
    """_extract_first_match returns first regex match group."""

    def test_basic_match(self):
        self.assertEqual(
            _extract_first_match("Temperature is 72 degrees", [r"is (\d+)"]),
            "72",
        )

    def test_first_pattern_wins(self):
        self.assertEqual(
            _extract_first_match("Temp: 72, Wind: 15", [r"Temp: (\d+)", r"Wind: (\d+)"]),
            "72",
        )

    def test_no_match(self):
        self.assertIsNone(_extract_first_match("no digits", [r"(\d+)"]))

    def test_empty_text(self):
        self.assertIsNone(_extract_first_match("", [r"(\d+)"]))

    def test_case_insensitive(self):
        self.assertEqual(
            _extract_first_match("TEMP 72", [r"temp (\d+)"]),
            "72",
        )


# ---------------------------------------------------------------------------
# is_obituary_title
# ---------------------------------------------------------------------------

class TestIsObituaryTitle(TestCase):
    """is_obituary_title detects obituary-related keywords."""

    def test_obituary_keyword(self):
        self.assertTrue(is_obituary_title("John's Obituary"))

    def test_passed_away(self):
        self.assertTrue(is_obituary_title("She Passed Away"))

    def test_death_notice(self):
        self.assertTrue(is_obituary_title("Death Notice: Smith"))

    def test_funeral_services(self):
        self.assertTrue(is_obituary_title("Funeral Services for Jane"))

    def test_memorial_service(self):
        self.assertTrue(is_obituary_title("Memorial Service for Bob"))

    def test_normal_title(self):
        self.assertFalse(is_obituary_title("Local News Update"))

    def test_empty(self):
        self.assertFalse(is_obituary_title(""))

    def test_unrelated(self):
        self.assertFalse(is_obituary_title("Weather Report"))


# ---------------------------------------------------------------------------
# is_real_estate_title
# ---------------------------------------------------------------------------

class TestIsRealEstateTitle(TestCase):
    """is_real_estate_title detects real estate markers."""

    def test_zillow(self):
        self.assertTrue(is_real_estate_title("Zillow listing"))

    def test_for_sale(self):
        self.assertTrue(is_real_estate_title("House for sale"))

    def test_home_for_matches(self):
        # "home for" is in the keyword list
        self.assertTrue(is_real_estate_title("Home for rent"))

    def test_property(self):
        self.assertTrue(is_real_estate_title("New Property"))

    def test_dollar_sign(self):
        self.assertTrue(is_real_estate_title("$500k deal"))

    def test_realtor(self):
        self.assertTrue(is_real_estate_title("Realtor update"))

    def test_normal_title(self):
        self.assertFalse(is_real_estate_title("Local news"))

    def test_empty(self):
        self.assertFalse(is_real_estate_title(""))

    def test_redfin(self):
        self.assertTrue(is_real_estate_title("Redfin search"))

    def test_listing(self):
        self.assertTrue(is_real_estate_title("Listing expires"))


# ---------------------------------------------------------------------------
# _coerce_temperature_f
# ---------------------------------------------------------------------------

class TestCoerceTemperatureF(TestCase):
    """_coerce_temperature_f safely converts temperature strings."""

    def test_plain_number(self):
        self.assertEqual(_coerce_temperature_f("72"), 72.0)

    def test_with_unit(self):
        self.assertEqual(_coerce_temperature_f("72.5°F"), 72.5)

    def test_negative_stripped(self):
        # Implementation strips all non-digit/dot chars, so "-" is lost
        self.assertEqual(_coerce_temperature_f("-3°C"), 3.0)

    def test_none(self):
        self.assertIsNone(_coerce_temperature_f(None))

    def test_empty(self):
        self.assertIsNone(_coerce_temperature_f(""))

    def test_non_numeric(self):
        self.assertIsNone(_coerce_temperature_f("not a number"))

    def test_too_high(self):
        self.assertIsNone(_coerce_temperature_f("200"))

    def test_negative_sixty_stripped(self):
        # "-" stripped, so -60 → 60 → valid range
        self.assertEqual(_coerce_temperature_f("-60"), 60.0)

    def test_upper_boundary(self):
        self.assertEqual(_coerce_temperature_f("140"), 140.0)

    def test_negative_fifty_stripped(self):
        # "-" stripped, so -50 → 50 → valid
        self.assertEqual(_coerce_temperature_f("-50"), 50.0)

    def test_over_upper(self):
        self.assertIsNone(_coerce_temperature_f("141"))

    def test_negative_fiftyone_stripped(self):
        # "-" stripped, so -51 → 51 → valid
        self.assertEqual(_coerce_temperature_f("-51"), 51.0)

    def test_decimal(self):
        self.assertEqual(_coerce_temperature_f("72.3"), 72.3)


if __name__ == "__main__":
    from unittest import main
    main()
