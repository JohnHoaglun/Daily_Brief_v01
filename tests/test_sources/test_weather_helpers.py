"""Unit tests for date/label helper functions in daily_brief/sources/weather.py."""

from datetime import datetime
from unittest import TestCase, mock
from zoneinfo import ZoneInfo

from daily_brief.sources.weather import (
    _parse_date_for_weather,
    get_reference_datetime,
    get_weather_label_for_offset,
)

CHICTZ = ZoneInfo("America/Chicago")


class TestParseDateForWeather(TestCase):
    """NWS forecast date string parsing — representative cases."""

    def test_iso_format(self):
        result = _parse_date_for_weather("2026-07-18T12:00:00Z")
        self.assertEqual(result.year, 2026)

    def test_no_tz_uses_default(self):
        result = _parse_date_for_weather("2026-07-18T08:00:00")
        self.assertEqual(result.tzinfo, CHICTZ)

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_date_for_weather("not-a-date"))
        self.assertIsNone(_parse_date_for_weather(""))
        self.assertIsNone(_parse_date_for_weather(None))


class TestGetWeatherLabelForOffset(TestCase):
    """Weather label generation for forecast offsets."""

    def test_offsets(self):
        ref = datetime(2026, 7, 18, 10, 0, 0, tzinfo=CHICTZ)
        self.assertEqual(get_weather_label_for_offset(ref, 0), "Sat")
        self.assertEqual(get_weather_label_for_offset(ref, 1), "Sun")
        self.assertEqual(get_weather_label_for_offset(ref, 2), "Mon")
        self.assertEqual(get_weather_label_for_offset(ref, -1), "Fri")


class TestGetReferenceDatetime(TestCase):
    """Reference datetime with optional override."""

    def test_returns_datetime_with_tz(self):
        dt = get_reference_datetime()
        self.assertIsNotNone(dt.tzinfo)

    def test_date_override(self):
        with mock.patch("daily_brief.sources.weather.DATE_OVERRIDE", "2026-01-15T10:00:00"):
            dt = get_reference_datetime()
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)
