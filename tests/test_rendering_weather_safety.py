"""
Rendering / Markdown Safety Contract — Weather fixtures.
========================================================
Documents the desired Markdown rendering safety behavior for
weather_table.py (table cell escaping).

Each fixture documents a known bug that must be fixed.

Known bugs targeted:
1. Pipe characters in weather table cells break Markdown table structure
2. Weather cell values with Markdown-special characters (~, _, `) unescaped
"""

from __future__ import annotations

from unittest import TestCase

from daily_brief.rendering.weather_table import build_weather_markdown


# ---------------------------------------------------------------------------
# 2. Pipe characters in weather table cells  (BUG)
# ---------------------------------------------------------------------------


class TestWeatherPipeSafety(TestCase):
    """Pipe (|) in weather values must not break Markdown table structure.

    A cell value containing | creates an extra column, breaking the table.
    Safe output: pipes in cell values must be escaped as \\| or HTML &middot;
    """

    def test_pipe_in_wind_value_breaks_table(self):
        """North|South wind in Wind cell creates extra column (8 pipes vs 7)."""
        weather = {
            "forecast": [
                {
                    "date": "Mon",
                    "day": "Sunny",
                    "night": "Clear",
                    "high": "85",
                    "low": "68",
                    "precip": "0%",
                    "wind": "North|South wind",
                },
                {
                    "date": "Tue",
                    "day": "Cloudy",
                    "night": "Clear",
                    "high": "80",
                    "low": "65",
                    "precip": "10%",
                    "wind": "5 mph",
                },
                {
                    "date": "Wed",
                    "day": "Clear",
                    "night": "Clear",
                    "high": "82",
                    "low": "66",
                    "precip": "5%",
                    "wind": "3 mph",
                },
            ],
        }
        result = build_weather_markdown(weather)
        # Row with the pipe-containing value
        for line in result:
            if "North" in line:
                # 7-column Markdown table with leading/trailing |: 8 pipes
                # Unescaped pipe in cell creates extra column: 9 pipes = broken
                pipe_count = line.count("|")
                self.assertEqual(
                    pipe_count,
                    8,
                    f"Row has {pipe_count} pipes (expected 8 for 7-column table). "
                    "Unescaped pipe in cell value broke table structure."
                    f" Row: {line!r}",
                )
                break
        else:
            self.fail("No row containing 'North' found in output.")

    def test_pipe_in_day_condition_breaks_table(self):
        """Sunny|Partly Cloudy in Day Condition cell breaks table."""
        weather = {
            "forecast": [
                {
                    "date": "Mon",
                    "day": "Sunny|Partly Cloudy",
                    "night": "Clear",
                    "high": "85",
                    "low": "68",
                    "precip": "0%",
                    "wind": "5 mph",
                },
                {
                    "date": "Tue",
                    "day": "Cloudy",
                    "night": "Clear",
                    "high": "80",
                    "low": "65",
                    "precip": "10%",
                    "wind": "5 mph",
                },
                {
                    "date": "Wed",
                    "day": "Clear",
                    "night": "Clear",
                    "high": "82",
                    "low": "66",
                    "precip": "5%",
                    "wind": "3 mph",
                },
            ],
        }
        result = build_weather_markdown(weather)
        for line in result:
            if "Sunny" in line and "Partly Cloudy" in line:
                pipe_count = line.count("|")
                self.assertEqual(
                    pipe_count,
                    8,
                    f"Row has {pipe_count} pipes (expected 8 for 7-column table). Row: {line!r}",
                )
                break
        else:
            self.fail("No row containing 'Sunny' and 'Partly Cloudy' found.")

    def test_pipe_in_station_value(self):
        """Pipe in station value also breaks the 2-column station table."""
        weather = {
            "forecast": [
                {
                    "date": "Mon",
                    "day": "Sunny",
                    "night": "Clear",
                    "high": "85",
                    "low": "68",
                    "precip": "0%",
                    "wind": "5 mph",
                },
                {
                    "date": "Tue",
                    "day": "Cloudy",
                    "night": "Clear",
                    "high": "80",
                    "low": "65",
                    "precip": "10%",
                    "wind": "5 mph",
                },
                {
                    "date": "Wed",
                    "day": "Clear",
                    "night": "Clear",
                    "high": "82",
                    "low": "66",
                    "precip": "5%",
                    "wind": "3 mph",
                },
            ],
            "station": {
                "avg_temp_today": "83|85",
                "avg_monthly_rainfall": "3.5 in",
                "current_monthly_rainfall": "2.1 in",
            },
        }
        result = build_weather_markdown(weather)
        for line in result:
            if "83" in line and "85" in line:
                pipe_count = line.count("|")
                # 2-column station table: | label | value | = 3 pipes
                # Escaped pipe (no literal | in value) keeps count at 3
                self.assertEqual(
                    pipe_count,
                    3,
                    f"Station row has {pipe_count} pipes (expected 3 for 2-column table). "
                    f"Row: {line!r}",
                )
                break


# ---------------------------------------------------------------------------
# 8. Weather cell values with Markdown characters  (BUG)
# ---------------------------------------------------------------------------


class TestWeatherMarkdownChars(TestCase):
    """Weather cell values with Markdown-special characters must render safely.

    Characters like ~, _, *, in weather values must not interfere with
    Markdown table rendering.
    """

    def test_tilde_in_day_condition(self):
        """~ in weather values might create strikethrough in some renderers."""
        weather = {
            "forecast": [
                {
                    "date": "Mon",
                    "day": "~Sunny",
                    "night": "Clear",
                    "high": "85",
                    "low": "68",
                    "precip": "0%",
                    "wind": "5 mph",
                },
                {
                    "date": "Tue",
                    "day": "Cloudy",
                    "night": "Clear",
                    "high": "80",
                    "low": "65",
                    "precip": "10%",
                    "wind": "5 mph",
                },
                {
                    "date": "Wed",
                    "day": "Clear",
                    "night": "Clear",
                    "high": "82",
                    "low": "66",
                    "precip": "5%",
                    "wind": "3 mph",
                },
            ],
        }
        result = build_weather_markdown(weather)
        joined = "\n".join(result)
        # ~Sunny in a table cell might be interpreted as strikethrough markup
        # in GFM. This test documents the current unsafe behavior.
        tilde_rows = [l for l in result if "~Sunny" in l]
        self.assertTrue(len(tilde_rows) > 0, "Row with ~Sunny not found")
        # Document: tilde is unescaped
        self.assertFalse(
            any("\\~" in l for l in tilde_rows),
            "UNSAFE (documented): tilde in weather value is not escaped. "
            "May render as strikethrough in GFM-compatible renderers.",
        )

    def test_underscore_in_wind(self):
        """_ in weather values might create italic in some renderers."""
        weather = {
            "forecast": [
                {
                    "date": "Mon",
                    "day": "Sunny",
                    "night": "Clear",
                    "high": "85",
                    "low": "68",
                    "precip": "0%",
                    "wind": "N_S_wind",
                },
                {
                    "date": "Tue",
                    "day": "Cloudy",
                    "night": "Clear",
                    "high": "80",
                    "low": "65",
                    "precip": "10%",
                    "wind": "5 mph",
                },
                {
                    "date": "Wed",
                    "day": "Clear",
                    "night": "Clear",
                    "high": "82",
                    "low": "66",
                    "precip": "5%",
                    "wind": "3 mph",
                },
            ],
        }
        result = build_weather_markdown(weather)
        joined = "\n".join(result)
        self.assertIn(
            "N_S_wind", joined, "UNSAFE (documented): underscore in weather value is not escaped."
        )

    def test_backtick_in_precip(self):
        """Backtick in weather values might create code formatting."""
        weather = {
            "forecast": [
                {
                    "date": "Mon",
                    "day": "Sunny",
                    "night": "Clear",
                    "high": "85",
                    "low": "68",
                    "precip": "`0`%",
                    "wind": "5 mph",
                },
                {
                    "date": "Tue",
                    "day": "Cloudy",
                    "night": "Clear",
                    "high": "80",
                    "low": "65",
                    "precip": "10%",
                    "wind": "5 mph",
                },
                {
                    "date": "Wed",
                    "day": "Clear",
                    "night": "Clear",
                    "high": "82",
                    "low": "66",
                    "precip": "5%",
                    "wind": "3 mph",
                },
            ],
        }
        result = build_weather_markdown(weather)
        joined = "\n".join(result)
        self.assertIn(
            "`0`%",
            joined,
            "UNSAFE (documented): backtick in weather value is not escaped. "
            "May create inline code formatting in table cell.",
        )
