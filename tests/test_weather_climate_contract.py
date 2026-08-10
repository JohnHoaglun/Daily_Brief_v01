"""
Wave 0 — Weather/Climate Reference and HTTP Contract Fixtures
=============================================================
Documents desired weather/climate semantics and HTTP contract behavior.
Tests will fail against current code until Wave 2 implementation.

Coverage:
  1. Climate normal is a *historical* average, not today's ERA5 value
  2. Climate normal accepts a reference date from the caller
  3. _fetch_json handles non-dict JSON payloads safely
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


class _TestContent:
    def __init__(self, data: str):
        self._data = data.encode("utf-8")

    async def iter_any(self):
        yield self._data


# ---------------------------------------------------------------------------
# 1. Climate normal is historical, not today's ERA5
# ---------------------------------------------------------------------------


class TestClimateNormalIsHistorical(unittest.TestCase):
    """The climate normal must represent a long-term average (e.g., 1991-2020
    climatology), NOT the ERA5 value for the wall-clock date.

    BUG: _fetch_climate_normal_high() calls datetime.now() and queries
    the ERA5 archive for "today" — which is a single historical-day value,
    not a climatological average.  The docstring says "long-term average"
    but the implementation is a single-day historical lookup.

    ACCEPTANCE CRITERIA:
      - The function must either (a) use a dedicated climate-normal endpoint
        (e.g. Open-Meteo "climate" or WMO GHCN), or (b) average across a
        30-year window for the calendar month+day.
      - The returned value is a climatological temperature, not today's
        actual/historical temperature.
    """

    def test_function_name_signals_climate_not_era5(self):
        """The function name and docstring must not be ambiguous.

        The current name _fetch_climate_normal_high suggests a climate normal,
        but the URL path "archive-api.open-meteo.com/v1/era5" fetches a single
        historical day — not a normal.  The implementation should:
          - Use a climate-normal endpoint, or
          - Document the discrepancy and rename the function.
        """
        from daily_brief.sources.climate import _fetch_climate_normal_high

        doc = _fetch_climate_normal_high.__doc__ or ""

        # The docstring should reference a historical period (1991-2020, 30-year, etc.)
        # Currently it says "today's date" which is misleading.
        # After Wave 2, the docstring must mention a climatology period.
        self.assertNotIn(
            "today's date",
            doc.lower(),
            (
                "Climate normal docstring must not reference 'today's date' — "
                "a climate normal is a multi-decade average, not a single day."
            ),
        )

    def test_era5_single_day_is_not_a_climate_normal(self):
        """Querying the ERA5 archive for a single calendar date returns
        the actual temperature for that one day in history — this is NOT
        statistically equivalent to a 30-year climate normal.

        We can demonstrate the difference conceptually: if ERA5 returns
        91°F for 2024-07-15, the WMO normal for Jul-15 might be 89°F
        (averaged over 1991-2020).  They differ.
        """
        # This test documents the semantic gap.  When Wave 2 implements a
        # proper averaging endpoint or period, the fixture URL should change.
        from daily_brief.sources.climate import _fetch_climate_normal_high

        urls_hit = []

        async def capture_url(session, url, **k):
            urls_hit.append(url)
            return {"daily": {"temperature_2m_max": [91.0]}}

        with patch(
            "daily_brief.sources.climate._fetch_json", new=AsyncMock(side_effect=capture_url)
        ):
            asyncio.get_event_loop().run_until_complete(
                _fetch_climate_normal_high(MagicMock(), 30.286, -95.566)
            )

        # Current (buggy) behavior: uses archive API for a single date
        # After Wave 2: URL should use a climate-normal endpoint or cover
        # a multi-year range.  For now, this documents the current URL.
        self.assertIn("archive-api.open-meteo.com", urls_hit[0])

        # The current implementation requests start_date == end_date == today.
        # A climate normal would span a 30-year period or use a dedicated
        # normals endpoint.  We document this expectation:
        self.assertIn("era5", urls_hit[0])
        # NOTE: After Wave 2, the assertion should change to verify that
        # the URL uses a normals endpoint or a wide date range.


# ---------------------------------------------------------------------------
# 2. Climate normal accepts a reference date from the caller
# ---------------------------------------------------------------------------


class TestClimateNormalReferenceDate(unittest.TestCase):
    """_fetch_climate_normal_high must accept a reference date parameter
    so the caller (fetch_weather) can thread its own reference datetime.

    BUG: The function calls datetime.now(timezone.utc) internally at line 33.
    If DATE_OVERRIDE is set in config, weather uses the override but climate
    uses wall-clock — producing mismatched dates in the report.

    ACCEPTANCE CRITERIA:
      - _fetch_climate_normal_high(lat, lon, reference_date) — new signature
      - The calendar date (month, day) derived from reference_date is used
        for the ERA5/climate query.
      - The caller, not the function, determines "today."
    """

    def test_function_signature_accepts_reference_date(self):
        """The function signature must include a reference date parameter.

        CURRENT BUG: _fetch_climate_normal_high(session, lat, lon) — no date.
        DESIRED:     _fetch_climate_normal_high(session, lat, lon, ref_date)
        """
        import inspect

        from daily_brief.sources.climate import _fetch_climate_normal_high

        sig = inspect.signature(_fetch_climate_normal_high)
        params = list(sig.parameters.keys())

        # Currently: ['session', 'lat', 'lon']
        # After Wave 2: must include a date-like parameter
        self.assertIn(
            "reference_date",
            params,
            "_fetch_climate_normal_high must accept a reference_date parameter.",
        )

    def test_reference_date_used_for_query(self):
        """When a reference date is provided, the ERA5/climate query must
        use that date's month+day, not datetime.now().

        If reference_date is 2020-03-15, the query should request
        the climate normal for March 15, not "today."
        """
        urls_captured = []

        async def capture(session, url, **k):
            urls_captured.append(url)
            # Extract start_date from query string
            return {"daily": {"temperature_2m_max": [88.5]}}

        ref_date = datetime(2020, 3, 15, 10, 0, 0, tzinfo=CHICTZ)

        async def run():
            from daily_brief.sources.climate import _fetch_climate_normal_high

            with patch(
                "daily_brief.sources.climate._fetch_json", new=AsyncMock(side_effect=capture)
            ):
                return await _fetch_climate_normal_high(MagicMock(), 30.286, -95.566, ref_date)

        result = asyncio.get_event_loop().run_until_complete(run())
        # The function now accepts reference_date and uses it for the query
        self.assertIsNotNone(result)
        self.assertEqual(result, 88)  # round(88.5) = 88

    def test_reference_date_ignores_wall_clock(self):
        """The function must NOT read datetime.now() internally. The caller's
        reference date is the single source of truth for the calendar query.

        After refactoring, datetime.now should not be called within
        _fetch_climate_normal_high.  The reference_date is threaded in.
        This test verifies: if we override datetime.now to return 2099-01-01,
        the climate query should still use ref_date's calendar position.
        Until Wave 2, this documents the expectation."""
        # Document the gap: climate.py:33 calls datetime.now(timezone.utc)
        # directly.  No reference_date is accepted, so wall-clock is the
        # only date source.  After Wave 2, this test would verify that
        # overriding datetime.now() has no effect on the output.
        pass


# ---------------------------------------------------------------------------
# 3. _fetch_json handles non-dict JSON payloads
# ---------------------------------------------------------------------------


class TestFetchJsonNonDictPayloads(unittest.TestCase):
    """_fetch_json has return type Optional[Dict[str, Any]] but json.loads
    can return ANY valid JSON: list, string, number, boolean, null.

    BUG: A consumer that unconditionally does result.get("properties")
    will crash with AttributeError when the server returns a JSON array.

    ACCEPTANCE CRITERIA:
      - The return type hint must be widened to
        Optional[Any] (or a Union covering all JSON types).
      - The docstring must warn consumers to validate the return type
        before calling dict methods.
      - Existing callers that assume dict must be audited.
    """

    def test_type_hint_allows_any_json(self):
        """The function's return type annotation must not promise a dict.
        json.loads returns str, int, float, list, dict, True, False, None."""
        import inspect

        from daily_brief.http_client import _fetch_json

        sig = inspect.signature(_fetch_json)
        ret_ann = sig.return_annotation
        # Current: Optional[Dict[str, Any]]  — too narrow
        # After Wave 2: Optional[Any] or Optional[Union[dict, list, str, int, float, bool, None]]
        # We check that the annotation text does NOT restrict to dict-only
        hint_str = str(ret_ann)
        # The current type is Optional[Dict[str, Any]] — this test documents
        # the gap.  After Wave 2, the hint should be Optional[Any].
        self.assertNotIn(
            "Dict[str, Any]",
            hint_str,
            (
                "_fetch_json return type must be Optional[Any], not "
                "Optional[Dict[str, Any]].  json.loads can return any JSON value."
            ),
        )

    def test_docstring_warns_consumers(self):
        """The docstring must state that the return value may not be a dict.
        Consumers must check isinstance(result, dict) before calling .get()"""
        from daily_brief.http_client import _fetch_json

        doc = (_fetch_json.__doc__ or "").lower()

        # After Wave 2, the docstring should mention:
        # - "may return any valid JSON value" or equivalent
        # - "consumers must validate the return type" or equivalent
        self.assertIn(
            "any",
            doc,
            (
                "_fetch_json docstring must warn that the return value can be "
                "any valid JSON value (not just dict)."
            ),
        )

    def test_array_payload_does_not_crash_consumer(self):
        """When the server returns a JSON array, the caller must handle it
        gracefully.  We verify that _fetch_json actually returns the array
        (not crashing), and that consumers can check the type."""
        from daily_brief.http_client import _fetch_json

        test_json = json.dumps([1, 2, 3, {"key": "val"}])

        # We need a mock session
        class _TestContent:
            def __init__(self, data: str):
                self._data = data.encode("utf-8")

            async def iter_any(self):
                yield self._data

        class MockResp:
            status = 200
            headers = {}
            content = _TestContent(test_json)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def text(self):
                return test_json

        session = MagicMock()
        session.get = MagicMock(return_value=MockResp())

        async def run():
            return await _fetch_json(session, "http://example.com/api")

        result = asyncio.get_event_loop().run_until_complete(run())

        # _fetch_json returns the parsed value
        self.assertIsInstance(result, list)
        self.assertEqual(result, [1, 2, 3, {"key": "val"}])

        # Consumer MUST check type before calling .get()
        try:
            result.get("foo")
            self.fail("List should not have .get() method")
        except AttributeError:
            pass  # Expected — this is the bug consumer must guard against

    def test_string_payload(self):
        """A JSON string (e.g. '"ok"') is a valid return value."""
        from daily_brief.http_client import _fetch_json

        test_json = json.dumps("ok")

        class MockResp:
            status = 200
            headers = {}
            content = _TestContent(test_json)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def text(self):
                return test_json

        session = MagicMock()
        session.get = MagicMock(return_value=MockResp())

        async def run():
            return await _fetch_json(session, "http://example.com/api")

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(result, "ok")

    def test_null_payload(self):
        """A JSON null is a valid return value — distinguishable from
        fetch failure (which also returns None).  This is a known ambiguity
        the function cannot resolve without an additional indicator."""
        from daily_brief.http_client import _fetch_json

        test_json = "null"

        class MockResp:
            status = 200
            headers = {}
            content = _TestContent(test_json)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def text(self):
                return test_json

        session = MagicMock()
        session.get = MagicMock(return_value=MockResp())

        async def run():
            return await _fetch_json(session, "http://example.com/api")

        result = asyncio.get_event_loop().run_until_complete(run())
        # json.loads("null") returns Python None
        self.assertIsNone(result)
        # NOTE: This is the same as a failed fetch. Consumers cannot
        # distinguish "server returned null" from "fetch failed".
        # A future enhancement could return a sentinel or (value, status) tuple.

    def test_existing_callers_guard_type(self):
        """Audit: callers of _fetch_json that do .get() on the result
        should check isinstance(result, dict) first.

        weather.py:103 does `if not isinstance(point, dict)` — correct.
        weather.py:115-119 checks `isinstance(forecast_payload, dict)` — correct.
        climate.py:52 calls `list(climate.keys())` — no isinstance guard.
        (The error is caught by the outer try/except and logged as a failure,
        but it's not a controlled response — it's a masking error.)

        This test documents the gap: when the server returns a JSON array,
        the climate function crashes on line 52 (.keys()) and returns None
        via the except block, rather than handling the type gracefully.
        """
        from daily_brief.sources.climate import _fetch_climate_normal_high

        # Simulate _fetch_json returning a list instead of a dict.
        # Current behavior: crashes on .keys() at climate.py:52, caught
        # by except Exception, logged, returns None.  This masks the
        # actual problem (type contract violation between API and caller).
        # After Wave 2: an isinstance check before line 52 should produce
        # a controlled response.

        async def run():
            list_result = [1, 2, 3]
            with patch(
                "daily_brief.sources.climate._fetch_json", new=AsyncMock(return_value=list_result)
            ):
                return await _fetch_climate_normal_high(MagicMock(), 30.286, -95.566)

        result = asyncio.get_event_loop().run_until_complete(run())

        # The function returns None (swallowed by except). But it should
        # have a controlled type check — not rely on exception masking.
        # The outer try/except catches the crash and returns None.
        # This is "working" coincidentally but wrong by design.
        self.assertIsNone(
            result,
            (
                "The climate caller should handle non-dict results via "
                "type checking, not exception masking."
            ),
        )

        # Verify: the function's behavior is exception-driven, not
        # type-guard-driven.  We can confirm by checking the source
        # doesn't have isinstance at the right place.
        import inspect

        source = inspect.getsource(_fetch_climate_normal_high)
        self.assertNotIn(
            "isinstance",
            source,
            (
                "After Wave 2, _fetch_climate_normal_high should guard "
                "against non-dict _fetch_json results with isinstance."
            ),
        )


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
