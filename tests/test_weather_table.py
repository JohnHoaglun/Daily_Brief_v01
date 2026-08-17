"""
Unit tests for daily_brief/rendering/weather_table.py.
"""

from daily_brief.rendering.weather_table import build_weather_markdown


def _full_weather():
    return {
        "forecast": [
            {"date": "Mon", "day": "Sunny", "night": "Clear", "high": "85", "low": "68", "precip": "0%", "wind": "5 mph"},
            {"date": "Tue", "day": "Cloudy", "night": "Rain", "high": "80", "low": "65", "precip": "60%", "wind": "10 mph"},
            {"date": "Wed", "day": "Partly Cloudy", "night": "Clear", "high": "82", "low": "66", "precip": "10%", "wind": "8 mph"},
        ],
        "station": {"avg_temp_today": "83", "avg_monthly_rainfall": "3.5 in", "current_monthly_rainfall": "2.1 in"},
        "lakes": {
            "conroe": {"today": "78%", "one_week_ago": "80%", "thirty_days_ago": "82%"},
            "travis": {"today": "92%", "one_week_ago": "93%", "thirty_days_ago": "94%"},
        },
    }


class TestWeatherTableRendering:
    def test_full_data_render(self):
        """Full data produces headers, rows, and delimiters."""
        result = build_weather_markdown(_full_weather())
        assert isinstance(result, list)
        assert all(isinstance(line, str) for line in result)
        assert result[2] == "## Weather Forecast"
        assert result[6] == "| **Date** | **Day Condition** | **Night Condition** | **High Temp** | **Low Temp** | **Precip. Chance** | **Wind** |"
        assert result[7] == "| --- | --- | --- | --- | --- | --- | --- |"
        assert result[-1] == "---"
        assert any("| Mon | Sunny |" in l for l in result)
        assert any("| Tue | Cloudy |" in l for l in result)
        assert any("| 83 |" in l for l in result)
        assert any("78%" in l for l in result)
        assert any("92%" in l for l in result)
        assert any("Lake Conroe" in l for l in result)

    def test_empty_forecast_fallback(self):
        """Empty forecast produces 3 Dynamic placeholder rows."""
        result = build_weather_markdown({"forecast": []})
        dynamic_lines = [l for l in result if "| Dynamic |" in l]
        assert len(dynamic_lines) == 3

    def test_invalid_forecast(self):
        """Missing/None forecast produces 3 Unavailable rows."""
        for inp in [{"forecast": None}, {}]:
            result = build_weather_markdown(inp)
            unavail = [l for l in result if "| Unavailable |" in l]
            assert len(unavail) >= 3

    def test_padding(self):
        """1 forecast row pads to 3 with Dynamic."""
        weather = {"forecast": [{"date": "Thu", "day": "Sunny", "night": "Clear", "high": "90", "low": "70", "precip": "0%", "wind": "3 mph"}]}
        result = build_weather_markdown(weather)
        assert any("| Thu |" in l for l in result)
        assert len([l for l in result if "| Dynamic |" in l]) == 2
