"""
Unit tests for src/daily_brief/rendering/weather_table.py.
"""
import os
import sys
from unittest import TestCase, mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from daily_brief.rendering.weather_table import build_weather_markdown


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
# 1.  Full data render
# ---------------------------------------------------------------------------

class TestFullDataRender(TestCase):
    """All weather data populated — forecast, station, lakes."""

    def test_return_type_is_list(self):
        result = build_weather_markdown(_full_weather())
        self.assertIsInstance(result, list)

    def test_list_items_are_strings(self):
        result = build_weather_markdown(_full_weather())
        for item in result:
            self.assertIsInstance(item, str)

    def test_non_empty_output(self):
        result = build_weather_markdown(_full_weather())
        self.assertGreater(len(result), 15)

    def test_contains_section_title(self):
        result = build_weather_markdown(_full_weather())
        self.assertTrue(any("## Weather Forecast" in line for line in result))

    def test_contains_forecast_header(self):
        result = build_weather_markdown(_full_weather())
        self.assertTrue(any("| **Date** |" in line for line in result))

    def test_contains_separator(self):
        result = build_weather_markdown(_full_weather())
        self.assertIn("---", result)

    def test_contains_forecast_rows(self):
        result = build_weather_markdown(_full_weather())
        line_count = sum(1 for line in result if "| Mon |" in line or "| Tue |" in line or "| Wed |" in line)
        self.assertEqual(line_count, 3)

    def test_contains_station_data(self):
        result = build_weather_markdown(_full_weather())
        self.assertTrue(any("83" in line for line in result))
        self.assertTrue(any("3.5 in" in line for line in result))
        self.assertTrue(any("2.1 in" in line for line in result))

    def test_contains_lake_data(self):
        result = build_weather_markdown(_full_weather())
        self.assertTrue(any("78%" in line for line in result))
        self.assertTrue(any("65%" in line for line in result))
        self.assertTrue(any("92%" in line for line in result))

    def test_starts_with_delimiter(self):
        result = build_weather_markdown(_full_weather())
        self.assertEqual(result[0], "")
        self.assertEqual(result[1], "---")

    def test_ends_with_delimiter(self):
        result = build_weather_markdown(_full_weather())
        self.assertEqual(result[-1], "---")


# ---------------------------------------------------------------------------
# 2.  Empty / missing forecast fallback
# ---------------------------------------------------------------------------

class TestEmptyForecast(TestCase):
    """Empty forecast falls back to 3× Dynamic rows."""

    def test_empty_forecast_fallback(self):
        result = build_weather_markdown({"forecast": []})
        dynamic_lines = [l for l in result if "| Dynamic |" in l]
        self.assertEqual(len(dynamic_lines), 3)

    def test_missing_forecast_key_fallback(self):
        result = build_weather_markdown({})
        dynamic_lines = [l for l in result if "| Dynamic |" in l]
        self.assertEqual(len(dynamic_lines), 3)


# ---------------------------------------------------------------------------
# 3.  Partial forecast padding
# ---------------------------------------------------------------------------

class TestPartialForecast(TestCase):
    """Forecast with 1 or 2 rows is padded to 3."""

    def test_one_row_padded_to_three(self):
        weather = {
            "forecast": [
                {"date": "Thu", "day": "Sunny", "night": "Clear", "high": "90", "low": "70", "precip": "0%", "wind": "3 mph"},
            ]
        }
        result = build_weather_markdown(weather)
        self.assertTrue(any("| Thu |" in line for line in result))
        dynamic_lines = [l for l in result if "| Dynamic |" in l]
        self.assertEqual(len(dynamic_lines), 2)

    def test_two_rows_padded_to_three(self):
        weather = {
            "forecast": [
                {"date": "Fri", "day": "Rain", "night": "Storm", "high": "75", "low": "60", "precip": "90%", "wind": "20 mph"},
                {"date": "Sat", "day": "Clear", "night": "Clear", "high": "80", "low": "62", "precip": "5%", "wind": "7 mph"},
            ]
        }
        result = build_weather_markdown(weather)
        self.assertTrue(any("| Fri |" in line for line in result))
        self.assertTrue(any("| Sat |" in line for line in result))
        dynamic_lines = [l for l in result if "| Dynamic |" in l]
        self.assertEqual(len(dynamic_lines), 1)


# ---------------------------------------------------------------------------
# 4.  Missing forecast capped at 3
# ---------------------------------------------------------------------------

class TestForecastCap(TestCase):
    """More than 3 forecast rows only renders 3."""

    def test_four_rows_capped_to_three(self):
        weather = {
            "forecast": [
                {"date": f"D{i}", "day": "A", "night": "B", "high": "80", "low": "60", "precip": "0%", "wind": "5"}
                for i in range(4)
            ]
        }
        result = build_weather_markdown(weather)
        forecast_lines = [l for l in result if l.startswith("| ") and any(f"| D{i} |" in l for i in range(4))]
        self.assertEqual(len(forecast_lines), 3)
        self.assertTrue(any("| D0 |" in l for l in result))
        self.assertTrue(any("| D1 |" in l for l in result))
        self.assertTrue(any("| D2 |" in l for l in result))
        self.assertFalse(any("| D3 |" in l for l in result))


# ---------------------------------------------------------------------------
# 5.  Station data — empty and missing
# ---------------------------------------------------------------------------

class TestStationData(TestCase):
    """Station values show Unavailable when missing."""

    def test_empty_station_dict(self):
        result = build_weather_markdown({"forecast": [], "station": {}})
        station_section = "\n".join(result)
        unavailable_count = station_section.count("Unavailable")
        self.assertGreater(unavailable_count, 2)

    def test_missing_station_key(self):
        result = build_weather_markdown({"forecast": []})
        station_section = "\n".join(result)
        unavailable_count = station_section.count("Unavailable")
        self.assertGreater(unavailable_count, 2)


# ---------------------------------------------------------------------------
# 6.  Lakes — empty
# ---------------------------------------------------------------------------

class TestLakesEmpty(TestCase):
    """Empty lakes produces no lake rows but structure is intact."""

    def test_empty_lakes_no_lake_rows(self):
        weather = {
            "forecast": [{"date": "Sun", "day": "Sunny", "night": "Clear", "high": "88", "low": "70", "precip": "0%", "wind": "5 mph"}],
            "lakes": {},
        }
        result = build_weather_markdown(weather)
        joined = "\n".join(result)
        self.assertIn("| Where |", joined)
        self.assertIn("| --- |", joined)
        self.assertTrue(any("---" in l for l in result))

    def test_missing_lakes_key(self):
        weather = {
            "forecast": [{"date": "Sun", "day": "Sunny", "night": "Clear", "high": "88", "low": "70", "precip": "0%", "wind": "5 mph"}],
        }
        result = build_weather_markdown(weather)
        self.assertIsInstance(result, list)
        self.assertTrue(any("---" in l for l in result))


# ---------------------------------------------------------------------------
# 7.  Lake label formatting
# ---------------------------------------------------------------------------

class TestLakeLabels(TestCase):
    """Lake labels are formatted correctly."""

    def test_simple_key_becomes_lake_name(self):
        with mock.patch("daily_brief.rendering.weather_table.WEATHER_LAKE_URLS", {"conroe": "http://x"}):
            weather = {"forecast": [], "lakes": {"conroe": {"today": "50%"}}}
            result = build_weather_markdown(weather)
            self.assertTrue(any("Lake Conroe" in line for line in result))

    def test_lake_prefix_not_doubled(self):
        with mock.patch("daily_brief.rendering.weather_table.WEATHER_LAKE_URLS", {"lake_travis": "http://x"}):
            weather = {"forecast": [], "lakes": {"lake_travis": {"today": "90%"}}}
            result = build_weather_markdown(weather)
            self.assertTrue(any("Lake Travis" in line for line in result))
            self.assertFalse(any("Lake Lake" in line for line in result))

    def test_key_with_hyphen(self):
        with mock.patch("daily_brief.rendering.weather_table.WEATHER_LAKE_URLS", {"corpus-christi": "http://x"}):
            weather = {"forecast": [], "lakes": {"corpus-christi": {"today": "70%"}}}
            result = build_weather_markdown(weather)
            self.assertTrue(any("Lake Corpus Christi" in line for line in result))


# ---------------------------------------------------------------------------
# 8.  Table structure
# ---------------------------------------------------------------------------

class TestTableStructure(TestCase):
    """Markdown table structure: headers, separators, delimiters."""

    def test_header_row(self):
        result = build_weather_markdown({})
        expected = "| **Date** | **Day Condition** | **Night Condition** | **High Temp** | **Low Temp** | **Precip. Chance** | **Wind** |"
        self.assertIn(expected, result)

    def test_separator_row(self):
        result = build_weather_markdown({})
        self.assertIn("| --- | --- | --- | --- | --- | --- | --- |", result)

    def test_section_title_present(self):
        result = build_weather_markdown({})
        self.assertIn("## Weather Forecast", result)

    def test_forecast_subtitle(self):
        result = build_weather_markdown({})
        self.assertIn("**3 Day forecast for 77316:**", result)

    def test_leading_trailing_delimiters(self):
        result = build_weather_markdown({})
        self.assertEqual(result[1], "---")
        self.assertEqual(result[-1], "---")


# ---------------------------------------------------------------------------
# 9.  Values with None / invalid data
# ---------------------------------------------------------------------------

class TestMissingValues(TestCase):
    """None and missing keys render as Unavailable."""

    def test_none_forecast_values(self):
        weather = {
            "forecast": [
                {"date": None, "day": None, "night": None, "high": None, "low": None, "precip": None, "wind": None},
                {"date": None, "day": None, "night": None, "high": None, "low": None, "precip": None, "wind": None},
                {"date": None, "day": None, "night": None, "high": None, "low": None, "precip": None, "wind": None},
            ]
        }
        result = build_weather_markdown(weather)
        joined = "\n".join(result)
        self.assertIn("Unavailable", joined)

    def test_missing_row_keys(self):
        weather = {"forecast": [{}, {}, {}]}
        result = build_weather_markdown(weather)
        joined = "\n".join(result)
        self.assertIn("Unavailable", joined)


# ---------------------------------------------------------------------------
# 10. Lake rows inherit WEATHER_LAKE_URLS config
# ---------------------------------------------------------------------------

class TestLakeConfig(TestCase):
    """Lake section respects WEATHER_LAKE_URLS configuration."""

    def test_empty_lake_urls_no_lake_rows(self):
        with mock.patch("daily_brief.rendering.weather_table.WEATHER_LAKE_URLS", {}):
            result = build_weather_markdown({"forecast": [], "lakes": {"something": {"today": "1%"}}})
            lake_header_idx = None
            for i, line in enumerate(result):
                if "| Where |" in line:
                    lake_header_idx = i
                    break
            self.assertIsNotNone(lake_header_idx)
            lake_data_lines = [result[i] for i in range(lake_header_idx, len(result)) if result[i].startswith("| L")]
            self.assertEqual(len(lake_data_lines), 0)
