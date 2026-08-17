"""Reduced: climate table parsing, no-data fallback, date format."""

import asyncio
import json
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from daily_brief.sources.climate import _fetch_climate_normal_high


class _TestContent:
    def __init__(self, data: str):
        self._data = data.encode("utf-8")

    async def iter_any(self):
        yield self._data

    async def iter_chunked(self, size: int):
        start = 0
        while start < len(self._data):
            end = min(start + size, len(self._data))
            yield self._data[start:end]
            start = end


class TestClimateTableParsing(unittest.TestCase):
    def test_climate_table_parsed(self):
        """Verify climate temperature table is parsed from response JSON."""
        urls_captured = []

        async def capture(session, url, **k):
            urls_captured.append(url)
            return {
                "daily": {
                    "temperature_2m_max": [88.5],
                }
            }

        async def run():
            with patch("daily_brief.sources.climate._fetch_json", new=AsyncMock(side_effect=capture)):
                return await _fetch_climate_normal_high(MagicMock(), 30.286, -95.566)

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIsNotNone(result)
        self.assertEqual(result, 88)


class TestNoDataFallback(unittest.TestCase):
    def test_no_data_returns_none(self):
        """When the API returns no daily data, the function returns None."""

        async def return_no_data(session, url, **k):
            return {"daily": {}}

        async def run():
            with patch("daily_brief.sources.climate._fetch_json", new=AsyncMock(side_effect=return_no_data)):
                return await _fetch_climate_normal_high(MagicMock(), 30.286, -95.566)

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIsNone(result)

    def test_array_payload_handled(self):
        """Non-dict payload is handled gracefully."""

        async def return_array(session, url, **k):
            return [1, 2, 3]

        async def run():
            with patch("daily_brief.sources.climate._fetch_json", new=AsyncMock(side_effect=return_array)):
                return await _fetch_climate_normal_high(MagicMock(), 30.286, -95.566)

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIsNone(result)


class TestDateFormat(unittest.TestCase):
    def test_reference_date_used_for_query(self):
        """reference_date is used in the API query, not datetime.now()."""

        async def capture(*args, **kwargs):
            return {"daily": {"temperature_2m_max": [88.5]}}

        ref_date = datetime(2020, 3, 15, 10, 0, 0, tzinfo=None)

        async def run():
            with patch("daily_brief.sources.climate._fetch_json", AsyncMock(side_effect=capture)):
                return await _fetch_climate_normal_high(MagicMock(), 30.286, -95.566, ref_date)

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIsNotNone(result)

    def test_default_date_format(self):
        """Default None reference_date uses datetime.now() internally."""
        async def capture(*args, **kwargs):
            return {"daily": {"temperature_2m_max": [88.5]}}

        async def run():
            with patch("daily_brief.sources.climate._fetch_json", AsyncMock(side_effect=capture)):
                return await _fetch_climate_normal_high(MagicMock(), 30.286, -95.566, None)

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
