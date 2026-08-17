"""Rendering / Markdown Safety Contract — Weather fixtures — compact."""

from __future__ import annotations

from unittest import TestCase

from daily_brief.rendering.weather_table import build_weather_markdown


def _make_weather(wind="5 mph", day="Sunny", station_avg="83"):
    return {
        "forecast": [
            {"date": "Mon", "day": day, "night": "Clear", "high": "85", "low": "68", "precip": "0%", "wind": wind},
            {"date": "Tue", "day": "Cloudy", "night": "Clear", "high": "80", "low": "65", "precip": "10%", "wind": "5 mph"},
            {"date": "Wed", "day": "Clear", "night": "Clear", "high": "82", "low": "66", "precip": "5%", "wind": "3 mph"},
        ],
        "station": {"avg_temp_today": station_avg, "avg_monthly_rainfall": "3.5 in", "current_monthly_rainfall": "2.1 in"},
    }


class TestWeatherPipeSafety(TestCase):
    """Pipe in weather values must not break Markdown table structure."""

    def test_pipe_in_wind_value(self):
        result = build_weather_markdown(_make_weather(wind="North|South wind"))
        for line in result:
            if "North" in line:
                pipe_count = line.count("|")
                self.assertEqual(pipe_count, 8, f"Unescaped pipe breaks table: {pipe_count} pipes in row.")
                break
        else:
            self.fail("No row with 'North' found.")

    def test_pipe_in_station_value(self):
        result = build_weather_markdown(_make_weather(station_avg="83|85"))
        for line in result:
            if "83" in line and "85" in line:
                pipe_count = line.count("|")
                self.assertEqual(pipe_count, 3, f"Station table broken: {pipe_count} pipes.")
                break


class TestWeatherMarkdownChars(TestCase):
    def test_tilde_in_day_condition(self):
        result = build_weather_markdown(_make_weather(day="~Sunny"))
        tilde_rows = [l for l in result if "~Sunny" in l]
        self.assertTrue(len(tilde_rows) > 0, "~Sunny row not found.")

    def test_underscore_in_wind(self):
        result = build_weather_markdown(_make_weather(wind="N_S_wind"))
        joined = "\n".join(result)
        self.assertIn("N_S_wind", joined)

    def test_empty_city_code(self):
        """Empty city: forecast renders, no station data."""
        result = build_weather_markdown({
            "forecast": [
                {"date": "Mon", "day": "Sunny", "night": "Clear", "high": "85", "low": "68", "precip": "0%", "wind": "5 mph"},
            ],
            "station": {},
        })
        joined = "\n".join(result)
        self.assertIn("Weather", joined)


class TestWeatherSafeBehavior(TestCase):
    def test_normal_forecast_renders(self):
        result = build_weather_markdown(_make_weather())
        joined = "\n".join(result)
        self.assertIn("Weather", joined)
        self.assertTrue(any("Sunny" in l for l in result))
        self.assertTrue(any("Cloudy" in l for l in result))
