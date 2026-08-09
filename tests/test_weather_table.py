"""
Unit tests for daily_brief/rendering/weather_table.py.
"""
from unittest import TestCase, mock

from daily_brief.rendering.weather_table import build_weather_markdown, _normalize_weather


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _full_weather():
    """Weather dict with forecast, station, and lakes all populated."""
    return {
        "forecast": [
            {"date": "Mon", "day": "Sunny", "night": "Clear", "high": "85", "low": "68", "precip": "0%", "wind": "5 mph"},
            {"date": "Tue", "day": "Cloudy", "night": "Rain", "high": "80", "low": "65", "precip": "60%", "wind": "10 mph"},
            {"date": "Wed", "day": "Partly Cloudy", "night": "Clear", "high": "82", "low": "66", "precip": "10%", "wind": "8 mph"},
        ],
        "station": {
            "avg_temp_today": "83",
            "avg_monthly_rainfall": "3.5 in",
            "current_monthly_rainfall": "2.1 in",
        },
        "lakes": {
            "conroe": {"today": "78%", "one_week_ago": "80%", "thirty_days_ago": "82%"},
            "corpus_christi": {"today": "65%", "one_week_ago": "66%", "thirty_days_ago": "68%"},
            "travis": {"today": "92%", "one_week_ago": "93%", "thirty_days_ago": "94%"},
        },
    }


# ---------------------------------------------------------------------------
# _normalize_weather
# ---------------------------------------------------------------------------

class TestNormalizeWeather(TestCase):
    """_normalize_weather sanitizes all degraded inputs into safe dicts."""

    def test_non_dict_inputs_produce_degraded_forecast(self):
        """None, scalar, list inputs all produce dict with 3-degraded forecast rows."""
        for inp in [None, "error", 42, []]:
            result = _normalize_weather(inp)
            self.assertIsInstance(result, dict)
            self.assertIn("forecast", result)
            self.assertEqual(len(result["forecast"]), 3)

    def test_missing_or_invalid_nested(self):
        """Missing or non-dict station/lakes are replaced with safe defaults."""
        result = _normalize_weather({})
        self.assertIn("station", result)
        self.assertIn("lakes", result)
        self.assertIsInstance(result["station"], dict)
        self.assertIsInstance(result["lakes"], dict)
        self.assertDictEqual(result["station"], {})
        self.assertDictEqual(result["lakes"], {})

        result2 = _normalize_weather({"forecast": [], "station": "bad", "lakes": None})
        self.assertIsInstance(result2["station"], dict)
        self.assertDictEqual(result2["station"], {})
        self.assertIsInstance(result2["lakes"], dict)

    def test_valid_passthrough(self):
        """Valid forecast, station, and lakes objects are preserved as-is."""
        inp = {
            "forecast": [{"date": "Mon", "day": "Sunny", "night": "Clear", "high": "90", "low": "70", "precip": "0%", "wind": "5"}],
            "station": {"avg_temp_today": "88"},
            "lakes": {"conroe": {"today": "78%"}},
        }
        result = _normalize_weather(inp)
        self.assertIs(result["forecast"], inp["forecast"])
        self.assertIs(result["station"], inp["station"])
        self.assertIs(result["lakes"], inp["lakes"])


# ---------------------------------------------------------------------------
# Golden output — full data render
# ---------------------------------------------------------------------------

class TestGoldenOutput(TestCase):
    """Full-data render: structural headers, representative values, delimiters."""

    def test_golden_full_data(self):
        result = build_weather_markdown(_full_weather())
        self.assertIsInstance(result, list)
        self.assertTrue(all(isinstance(line, str) for line in result))
        self.assertGreater(len(result), 15)

        # Structure
        self.assertEqual(result[0], "")
        self.assertEqual(result[1], "---")
        self.assertEqual(result[2], "## Weather Forecast")
        self.assertEqual(result[4], "**3 Day forecast:**")
        self.assertEqual(result[6], "| **Date** | **Day Condition** | **Night Condition** | **High Temp** | **Low Temp** | **Precip. Chance** | **Wind** |")
        self.assertEqual(result[7], "| --- | --- | --- | --- | --- | --- | --- |")
        self.assertEqual(result[-1], "---")

        # Forecast rows
        self.assertIn("| Mon | Sunny | Clear | 85 | 68 | 0% | 5 mph |", result)
        self.assertIn("| Tue | Cloudy | Rain | 80 | 65 | 60% | 10 mph |", result)
        self.assertIn("| Wed | Partly Cloudy | Clear | 82 | 66 | 10% | 8 mph |", result)

        # Station
        self.assertIn("| 83 |", " ".join(result))
        self.assertIn("| 3.5 in |", " ".join(result))
        self.assertIn("| 2.1 in |", " ".join(result))

        # Lake data values
        self.assertIn("78%", " ".join(result))
        self.assertIn("65%", " ".join(result))
        self.assertIn("92%", " ".join(result))


# ---------------------------------------------------------------------------
# Empty-list forecast → 3× Dynamic rows
# ---------------------------------------------------------------------------

class TestEmptyForecast(TestCase):
    """Empty forecast list produces 3 Dynamic placeholder rows."""

    def test_empty_forecast_fallback(self):
        result = build_weather_markdown({"forecast": []})
        dynamic_lines = [l for l in result if "| Dynamic |" in l]
        self.assertEqual(len(dynamic_lines), 3)


# ---------------------------------------------------------------------------
# Missing / invalid forecast data → 3× Unavailable rows
# ---------------------------------------------------------------------------

class TestMissingForecast(TestCase):
    """Missing, None, or non-list forecast produces 3 Unavailable rows."""

    def test_invalid_forecast_data(self):
        for inp in [{}, None, "error", {"forecast": None}]:
            result = build_weather_markdown(inp)
            self.assertIsInstance(result, list)
            unavail_lines = [l for l in result if "| Unavailable |" in l]
            self.assertGreaterEqual(len(unavail_lines), 3, f"Expected ≥3 Unavailable rows for input {inp!r}")


# ---------------------------------------------------------------------------
# Padding (1/2 rows) and truncation (>3 rows)
# ---------------------------------------------------------------------------

class TestPaddingAndTruncation(TestCase):
    """1–2 forecast rows pad to 3 with Dynamic; >3 rows truncate to 3."""

    def test_one_row_padded(self):
        weather = {"forecast": [{"date": "Thu", "day": "Sunny", "night": "Clear", "high": "90", "low": "70", "precip": "0%", "wind": "3 mph"}]}
        result = build_weather_markdown(weather)
        self.assertTrue(any("| Thu |" in l for l in result))
        self.assertEqual(len([l for l in result if "| Dynamic |" in l]), 2)

    def test_two_rows_padded(self):
        weather = {"forecast": [
            {"date": "Fri", "day": "Rain", "night": "Storm", "high": "75", "low": "60", "precip": "90%", "wind": "20 mph"},
            {"date": "Sat", "day": "Clear", "night": "Clear", "high": "80", "low": "62", "precip": "5%", "wind": "7 mph"},
        ]}
        result = build_weather_markdown(weather)
        self.assertTrue(any("| Fri |" in l for l in result))
        self.assertTrue(any("| Sat |" in l for l in result))
        self.assertEqual(len([l for l in result if "| Dynamic |" in l]), 1)

    def test_over_three_truncated(self):
        weather = {"forecast": [
            {"date": f"D{i}", "day": "A", "night": "B", "high": "80", "low": "60", "precip": "0%", "wind": "5"}
            for i in range(4)
        ]}
        result = build_weather_markdown(weather)
        self.assertTrue(any("| D0 |" in l for l in result))
        self.assertTrue(any("| D1 |" in l for l in result))
        self.assertTrue(any("| D2 |" in l for l in result))
        self.assertFalse(any("| D3 |" in l for l in result))
        self.assertEqual(len([l for l in result if "| Dynamic |" in l]), 0)


# ---------------------------------------------------------------------------
# Lake ordering and label formatting
# ---------------------------------------------------------------------------

class TestLakeOrderingAndLabels(TestCase):
    """Lake rows respect config order; labels are title-cased with 'Lake' prefix."""

    def test_lake_ordering_and_label_formatting(self):
        result = build_weather_markdown(_full_weather())
        joined = "\n".join(result)

        # All 3 data lakes appear with correct label formatting
        self.assertIn("Lake Conroe", joined)
        self.assertIn("Lake Travis", joined)
        self.assertIn("Lake Corpus Christi", joined)

        # No "Lake Lake" duplication for keys that would title to start with "Lake"
        self.assertFalse(any("Lake Lake" in l for l in result))

        # Data values present on the right lake rows
        self.assertRegex(joined, r"\| Lake Conroe \| 78% \|")
        self.assertRegex(joined, r"\| Lake Travis \| 92% \|")

        # Hyphenated keys via mock
        with mock.patch("daily_brief.rendering.weather_table.WEATHER_LAKE_URLS", {"corpus-christi": "http://x"}):
            r2 = build_weather_markdown({"forecast": [], "lakes": {"corpus-christi": {"today": "70%"}}})
            self.assertTrue(any("Lake Corpus Christi" in l for l in r2))

        # Prefix not doubled for keys starting with "lake_"
        with mock.patch("daily_brief.rendering.weather_table.WEATHER_LAKE_URLS", {"lake_travis": "http://x"}):
            r3 = build_weather_markdown({"forecast": [], "lakes": {"lake_travis": {"today": "90%"}}})
            self.assertTrue(any("Lake Travis" in l for l in r3))
            self.assertFalse(any("Lake Lake" in l for l in r3))
