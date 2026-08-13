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


# _parse_date_for_weather
class TestParseDateForWeather(TestCase):
    """NWS forecast date string parsing — representative cases."""

    def test_iso_format_with_z(self):
        result = _parse_date_for_weather("2026-07-18T12:00:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 7)
        self.assertEqual(result.day, 18)

    def test_strptime_no_tz_uses_default(self):
        result = _parse_date_for_weather("2026-07-18T08:00:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, CHICTZ)

    def test_bracket_tz_format(self):
        result = _parse_date_for_weather("2026-07-18T20:00:00-05:00[America/Chicago]")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_date_for_weather("not-a-date"))
        self.assertIsNone(_parse_date_for_weather(""))
        self.assertIsNone(_parse_date_for_weather(None))


# get_weather_label_for_offset
class TestGetWeatherLabelForOffset(TestCase):
    """Weather label generation for forecast offsets."""

    def _ref(self, year=2026, month=7, day=18):
        return datetime(year, month, day, 10, 0, 0, tzinfo=CHICTZ)

    def test_offsets(self):
        ref = self._ref()  # 2026-07-18 is Saturday
        self.assertEqual(get_weather_label_for_offset(ref, 0), "Sat")
        self.assertEqual(get_weather_label_for_offset(ref, 1), "Sun")
        self.assertEqual(get_weather_label_for_offset(ref, 2), "Mon")
        self.assertEqual(get_weather_label_for_offset(ref, -1), "Fri")
        self.assertEqual(get_weather_label_for_offset(ref, -7), "Sat")


# get_reference_datetime
class TestGetReferenceDatetime(TestCase):
    """Reference datetime with optional override."""

    def test_returns_datetime_with_tz(self):
        dt = get_reference_datetime()
        self.assertIsNotNone(dt.tzinfo)

    def test_date_override_and_fallback(self):
        with mock.patch("daily_brief.sources.weather.DATE_OVERRIDE", "2026-01-15T10:00:00"):
            dt = get_reference_datetime()
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)

        with mock.patch("daily_brief.sources.weather.DATE_OVERRIDE", "bad-value"):
            dt2 = get_reference_datetime()
        self.assertIsNotNone(dt2)
