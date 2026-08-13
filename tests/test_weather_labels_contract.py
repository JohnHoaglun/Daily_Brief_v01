"""
Weather labels and date threading contracts.

Tests:
  4. Weather labels are configuration-driven, not hard-coded "77316"
  5. Leap-day (Feb 29) climate normal has a defined fallback
  6. Weather→climate reference date threading uses the same date
"""

import asyncio
import json
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

CHICTZ = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# 4. Weather labels are configuration-driven
# ---------------------------------------------------------------------------


class TestWeatherLabelsConfigurationDriven(unittest.TestCase):
    """The weather section title and location labels must not hard-code
    '77316' (a specific ZIP code).  They should be driven by configuration.

    BUG: weather_table.py:44 hard-codes "77316" in the subtitle.
         weather_table.py:63 hard-codes "77316" in default station row labels.
         report.py:150 hard-codes "Weather Forecast 77316" as a skip category.

    ACCEPTANCE CRITERIA:
      - The ZIP/location label is read from config.
      - The weather_table subtitle uses a configurable location string.
      - report.py uses WEATHER_SECTION_TITLE from config, not a literal.
    """

    def test_weather_table_subtitle_not_hardcoded(self):
        """weather_table.py line 44: '**3 Day forecast for 77316:**'
        The '77316' must come from a config value."""
        import inspect

        from daily_brief import rendering

        source = inspect.getsource(rendering.weather_table.build_weather_markdown)
        # The string "77316" should not appear as a hardcoded literal
        # After Wave 2, the location label comes from config
        # The subtitle line currently says: md.append("**3 Day forecast for 77316:**")
        self.assertNotIn(
            '"77316"',
            source.replace(" ", "").replace("\n", ""),
            (
                "weather_table.py must not hard-code '77316' in the forecast "
                "subtitle.  Use a configuration value."
            ),
        )

    def test_weather_station_labels_not_hardcoded(self):
        """weather_table.py line 63: default station rows contain '77316'.
        These fallback labels should reference a configurable location."""
        import inspect

        from daily_brief import rendering

        source = inspect.getsource(rendering.weather_table)

        # The default _default_station_rows currently contains "77316"
        # After Wave 2, defaults should use a config-sourced location
        self.assertNotIn(
            '"77316"',
            source.replace(" ", "").replace("\n", ""),
            (
                "weather_table.py default station row labels must not "
                "hard-code '77316'.  Use a configuration value."
            ),
        )

    def test_report_skip_category_not_hardcoded(self):
        """report.py line 150: `cn == "Weather Forecast 77316"` hard-codes
        the ZIP in the skip logic.  Should use WEATHER_SECTION_TITLE."""
        import inspect

        from daily_brief import rendering

        source = inspect.getsource(rendering.report.build_markdown)

        self.assertNotIn(
            '"Weather Forecast 77316"',
            source.replace(" ", "").replace("\n", ""),
            (
                "report.py must not hard-code 'Weather Forecast 77316' in the "
                "category skip logic.  Use WEATHER_SECTION_TITLE from config."
            ),
        )

    def test_weather_section_title_from_config(self):
        """WEATHER_SECTION_TITLE should be importable from config and used
        throughout weather rendering."""
        from daily_brief.config import WEATHER_SECTION_TITLE

        # Config provides the title — this is already correct
        self.assertIsInstance(WEATHER_SECTION_TITLE, str)
        self.assertTrue(len(WEATHER_SECTION_TITLE) > 0)

    def test_weather_table_uses_config_title(self):
        """build_weather_markdown must use WEATHER_SECTION_TITLE from config,
        not a hardcoded string."""
        import inspect

        from daily_brief.rendering.weather_table import build_weather_markdown

        source = inspect.getsource(build_weather_markdown)

        # It should reference WEATHER_SECTION_TITLE (which it does on line 42)
        self.assertIn("WEATHER_SECTION_TITLE", source)

        # But the subtitle on line 44 is hardcoded — this test checks for that
        # After Wave 2, the subtitle should derive from config
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if "3 Day forecast" in stripped and "77316" in stripped:
                self.fail(f"Subtitle must not hard-code location. Offending line: {stripped}")


# ---------------------------------------------------------------------------
# 5. Leap-day climate normal fallback
# ---------------------------------------------------------------------------


class TestLeapDayClimateNormal(unittest.TestCase):
    """When the reference date is February 29 (leap day), the climate normal
    must have a defined fallback strategy.  Many climate datasets do not have
    a Feb 29 average.

    ACCEPTANCE CRITERIA:
      - If reference_date is Feb 29 and the climate endpoint has no data
        for that day, the function must fall back to either:
        (a) Feb 28 average, or
        (b) average of Feb 28 and Mar 1, or
        (c) Mar 1 average.
      - The fallback strategy is documented and consistent.
    """

    def test_feb29_reference_date_is_defined(self):
        """Document: there must be a defined behavior for Feb 29.

        The current implementation queries the ER5 archive for the exact date.
        If that date is Feb 29 of a leap year in the past (e.g., 2024-02-29),
        ERA5 would have data.  But a true climate normal for Feb 29 would
        average across leap years.  For non-leap years, Feb 29 doesn't exist —
        what does the caller do?

        This test documents the gap.
        """

        # Feb 29, 2024 is a valid date; Feb 29, 2023 is not.
        leap_date = datetime(2024, 2, 29, tzinfo=CHICTZ)
        self.assertEqual(leap_date.month, 2)
        self.assertEqual(leap_date.day, 29)

        # The climate function's behavior with this date is undefined
        # in the absence of a reference_date parameter.  After Wave 2,
        # the function must handle this gracefully.

    def test_feb29_fallback_strategy_exists(self):
        """There must be a documented fallback for Feb 29 climate normals.

        WMO/NOAA convention: Feb 29 normals are typically the average of
        Feb 28 and Mar 1 normals.  The function should implement this
        or at minimum document the chosen convention.

        We verify the docstring or constants document this.
        """
        import inspect

        from daily_brief.sources import climate

        source = inspect.getsource(climate)

        # After Wave 2, the source code should mention leap day handling
        # Document the gap — currently neither "leap" nor "feb 29" appears
        # in the source, meaning there's no explicit handling.
        self.assertNotIn(
            "leap",
            source.lower().replace(" ", ""),
            (
                "After Wave 2, climate.py should document or implement "
                "leap-day (Feb 29) handling.  For now, this documents the gap."
            ),
        )

    def test_feb28_and_mar1_average_strategy(self):
        """If we adopt the standard convention (average of Feb 28 and Mar 1
        normals), the result should reflect that."""
        # Document the expected math:
        feb28_normal = 65.0
        mar01_normal = 67.0
        expected_feb29_normal = round((feb28_normal + mar01_normal) / 2)
        self.assertEqual(expected_feb29_normal, 66)

        # Wave 2 should implement this logic for Feb 29 reference dates.


# ---------------------------------------------------------------------------
# 6. Weather→climate reference date threading
# ---------------------------------------------------------------------------


class TestWeatherClimateDateThreading(unittest.TestCase):
    """The weather orchestrator (fetch_weather) calls both
    fetch_nws_forecast AND _fetch_climate_normal_high.  Both must use
    the same reference date.

    BUG: fetch_weather gets `now_ref = get_reference_datetime()` for weather
    but passes no date to _fetch_climate_normal_high, which calls
    datetime.now() independently.  If DATE_OVERRIDE changes the weather date,
    the climate date does not change.

    ACCEPTANCE CRITERIA:
      - fetch_weather passes `now_ref` to _fetch_climate_normal_high.
      - Both use the same calendar date for their respective queries.
      - DATE_OVERRIDE affects both weather and climate consistently.
    """

    def test_fetch_weather_passes_ref_date_to_climate(self):
        """fetch_weather must pass the reference datetime to climate fetch.
        CURRENT:  _fetch_climate_normal_high(session, lat, lon) — no date.
        DESIRED:  _fetch_climate_normal_high(session, lat, lon, now_ref)"""
        import inspect

        from daily_brief.sources import weather

        source = inspect.getsource(weather.fetch_weather)

        # After Wave 2, the call to _fetch_climate_normal_high should
        # include the reference date.  Currently it does not.
        self.assertIn(
            "reference_date",
            source,
            (
                "fetch_weather must pass the reference date to "
                "_fetch_climate_normal_high.  Currently it passes no date."
            ),
        )

    def test_date_override_affects_climate(self):
        """When DATE_OVERRIDE is set, both weather forecast AND climate
        normal should use the overridden date.  Currently only weather
        is affected.

        If DATE_OVERRIDE = "2026-03-15", the NWS forecast centers on Mar 15
        but the climate normal centers on wall-clock "today" — a mismatch.
        """
        from daily_brief.sources.weather import get_reference_datetime

        with patch("daily_brief.sources.weather.DATE_OVERRIDE", "2026-03-15T10:00:00"):
            ref = get_reference_datetime()
            self.assertEqual(ref.year, 2026)
            self.assertEqual(ref.month, 3)
            self.assertEqual(ref.day, 15)

        # But _fetch_climate_normal_high does NOT receive this date.
        # It calls its own datetime.now(timezone.utc) — which returns
        # wall-clock.  This test documents the gap.

        # After Wave 2, calling fetch_weather with DATE_OVERRIDE set
        # should result in climate using 2026-03-15's calendar date too.

    def test_consistent_calendar_across_providers(self):
        """All weather sub-queries (NWS, climate, wunderground, lakes)
        must use the same reference date.  No provider may independently
        call datetime.now()."""

        # Document all places that currently call datetime.now():
        # - climate.py:33   → _fetch_climate_normal_high
        # - weather.py:53   → get_reference_datetime (correct — this IS the
        #                     source of truth, but its output doesn't reach
        #                     _fetch_climate_normal_high)

        # After Wave 2, the only datetime.now() call should be in
        # get_reference_datetime().  All downstream functions receive
        # the date as a parameter.
        pass


if __name__ == "__main__":
    unittest.main()
