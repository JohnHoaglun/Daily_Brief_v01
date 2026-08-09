from daily_brief.validation_harness import parse_log, parse_output, run_checks


VALID_LOG_FIXTURE = """\
[2026-08-04 01:05:30] ============================================================
[2026-08-04 01:05:30] DAILY BRIEF v1.0.109 - Pipeline Starting
[2026-08-04 01:05:30]   Weather OK -- 3 forecast periods | 1 station record | 11 lake sources
[2026-08-04 01:05:30]   Phase 1 completed in 5.23s
[2026-08-04 01:05:35]   Phase 2 completed in 3.45s
[2026-08-04 01:06:35]   Phase 3 completed in 54.71s
[2026-08-04 01:06:35]   Phase 4 completed in 0.19s
[2026-08-04 01:06:35]   Phase 5 completed in 0.01s
[2026-08-04 01:06:35] TOTAL PIPELINE TIME: 63.59s
"""

VALID_REPORT_FIXTURE = """\
---
title: Daily Brief
date: 2026-08-04
time_generated: 2026-08-04T01:06:35Z
status: active
content_age_window: 48
story_count_total: 1
categories: 1
tags:
  - test
---

## Weather Forecast

**3 Day forecast for 77316:**

| Tuesday | Partly Cloudy | Clear | 95°F | 75°F | 20% | 10 mph SW |
| Tonight | Clear | Clear | 85°F | 70°F | 10% | 5 mph S |
| Wednesday | Partly Cloudy | Partly Cloudy | 92°F | 73°F | 30% | 15 mph SW |

| Climate Normal High for today 77316 | 93°F |
| Average Monthly rainfall for 77316 | 3.75 Inches |
| Current Monthly rainfall for 77316 | 2.10 Inches |

| Where | Today | 1 Week Ago | 30 Days ago |
| --- | --- | --- | --- |
| Lake Conroe | 85.2% | 84.1% | 80.5% |
| Lake Houston | 78.9% | 77.5% | 75.2% |

## World News (1 stories)

1. [Test Story](https://example.com/1)
   Test summary sentence.
*Originally published on:* Aug 4, 2026

[[#world]]
"""

INVALID_REPORT_FIXTURE = """\
---
title: Daily Brief
date: 2026-08-04
time_generated: 2026-08-04T01:06:35Z
status: active
content_age_window: 48
story_count_total: 1
categories: 1
tags:
  - test
---

## Weather Forecast

**3 Day forecast for 77316:**

| Tuesday | Partly Cloudy | Clear | 95°F | 75°F | 20% | 10 mph SW |
| Tonight | Clear | Clear | 85°F | 70°F | 10% | 5 mph S |
| Wednesday | Partly Cloudy | Partly Cloudy | 92°F | 73°F | 30% | 15 mph SW |

| Climate Normal High for today 77316 | Unavailable |
| Average Monthly rainfall for 77316 | Unavailable |
| Current Monthly rainfall for 77316 | Unavailable |

| Where | Today | 1 Week Ago | 30 Days ago |
| --- | --- | --- | --- |
| Lake Conroe | 85.2% | 84.1% | 80.5% |
| Lake Houston | 78.9% | 77.5% | 75.2% |

## World News (1 stories)

1. [Test Story](https://example.com/1)
   Test summary sentence.
*Originally published on:* Aug 4, 2026

[[#world]]
"""

LOG_WITH_STATION = """\
[2026-08-04 01:05:30] Weather OK -- 3 forecast periods | 1 station record | 11 lake sources
[2026-08-04 01:05:30] [fetch_weather] Station data complete: avg_temp_today=93°F avg_monthly_rainfall=3.77 Inches current_monthly_rainfall=2.10 Inches
[2026-08-04 01:05:30] Phase 1 completed in 5.23s
[2026-08-04 01:05:35] Phase 2 completed in 3.45s
[2026-08-04 01:06:35] Phase 3 completed in 54.71s
[2026-08-04 01:06:35] Phase 4 completed in 0.19s
"""

REPORT_NO_FORECAST = """\
---
title: Daily Brief
date: 2026-08-04
time_generated: 2026-08-04T01:06:35Z
status: active
content_age_window: 48
story_count_total: 1
categories: 1
tags:
  - test
---

## Weather Forecast

| Where | Today | 1 Week Ago | 30 Days ago |
| --- | --- | --- | --- |
| Lake Conroe | 85.2% | 84.1% | 80.5% |

## World News (1 stories)

1. [Test Story](https://example.com/1)
   Test summary sentence.
*Originally published on:* Aug 4, 2026

[[#world]]
"""

REPORT_PARTIAL_STATION = """\
---
title: Daily Brief
date: 2026-08-04
time_generated: 2026-08-04T01:06:35Z
status: active
content_age_window: 48
story_count_total: 1
categories: 1
tags:
  - test
---

## Weather Forecast

**3 Day forecast for 77316:**

| Tuesday | Partly Cloudy | Clear | 95°F | 75°F | 20% | 10 mph SW |
| Tonight | Clear | Clear | 85°F | 70°F | 10% | 5 mph S |
| Wednesday | Partly Cloudy | Partly Cloudy | 92°F | 73°F | 30% | 15 mph SW |

| Climate Normal High for today 77316 | 93°F |
| Average Monthly rainfall for 77316 | 3.75 Inches |
| Current Monthly rainfall for 77316 | Unavailable |

| Where | Today | 1 Week Ago | 30 Days ago |
| --- | --- | --- | --- |
| Lake Conroe | 85.2% | 84.1% | 80.5% |
| Lake Houston | 78.9% | 77.5% | 75.2% |

## World News (1 stories)

1. [Test Story](https://example.com/1)
   Test summary sentence.
*Originally published on:* Aug 4, 2026

[[#world]]
"""

MINIMAL_CONFIG = {
    "weather": {
        "lake_urls": {
            "Lake Conroe": "http://x",
            "Lake Houston": "http://x",
        }
    },
    "directories": {
        "news_dir": "/fake/news/dir",
    },
}


class TestParseLog:

    def test_forecast_periods_from_current_log(self):
        data = parse_log(VALID_LOG_FIXTURE)
        assert data["forecast_periods"] == 3

    def test_phase_timings(self):
        data = parse_log(VALID_LOG_FIXTURE)
        assert data["phase_timings"][1] == 5.23
        assert data["phase_timings"][2] == 3.45
        assert data["phase_timings"][3] == 54.71
        assert data["phase_timings"][4] == 0.19


class TestParseOutput:

    def test_forecast_row_count_valid(self):
        data = parse_output(VALID_REPORT_FIXTURE)
        assert data["forecast_row_count"] == 3

    def test_station_values_valid(self):
        data = parse_output(VALID_REPORT_FIXTURE)
        assert data["station_values"]["avg_temp_today"] == "93°F"
        assert data["station_values"]["avg_monthly_rainfall"] == "3.75 Inches"
        assert data["station_values"]["current_monthly_rainfall"] == "2.10 Inches"

    def test_station_values_unavailable(self):
        data = parse_output(INVALID_REPORT_FIXTURE)
        assert data["station_values"]["avg_temp_today"] == "Unavailable"
        assert data["station_values"]["avg_monthly_rainfall"] == "Unavailable"
        assert data["station_values"]["current_monthly_rainfall"] == "Unavailable"

    def test_forecast_row_count_zero_with_no_data(self):
        data = parse_output(REPORT_NO_FORECAST)
        assert data["forecast_row_count"] == 0

    def test_lake_rows_parsed(self):
        data = parse_output(VALID_REPORT_FIXTURE)
        assert len(data["lake_rows"]) >= 2
        assert "Conroe" in data["lake_rows"]
        assert "Houston" in data["lake_rows"]


class TestRunChecks:

    def test_phase1_passes_for_valid_data(self):
        log_data = parse_log(LOG_WITH_STATION)
        out_data = parse_output(VALID_REPORT_FIXTURE)
        results = run_checks(MINIMAL_CONFIG, log_data, out_data, None, None)
        fails = results.by_level("FAIL")
        fail_ids = [cid for cid, _ in fails]
        assert "1.2" not in fail_ids, f"Check 1.2 should pass, got fails: {fails}"
        assert "1.3" not in fail_ids, f"Check 1.3 should pass, got fails: {fails}"

    def test_phase1_fails_when_no_forecast_rows(self):
        log_data = parse_log(LOG_WITH_STATION)
        out_data = parse_output(REPORT_NO_FORECAST)
        results = run_checks(MINIMAL_CONFIG, log_data, out_data, None, None)
        fail_ids = [cid for cid, _ in results.by_level("FAIL")]
        assert "1.2" in fail_ids, f"Check 1.2 should fail for 0 forecast rows, got: {fail_ids}"

    def test_phase1_fails_when_station_unavailable(self):
        log_data = parse_log(VALID_LOG_FIXTURE)
        out_data = parse_output(INVALID_REPORT_FIXTURE)
        results = run_checks(MINIMAL_CONFIG, log_data, out_data, None, None)
        fail_ids = [cid for cid, _ in results.by_level("FAIL")]
        assert "1.3" in fail_ids, f"Check 1.3 should fail for missing station data in log, got: {fail_ids}"

    def test_stations_tolerate_unavailable_rainfall_field(self):
        log_data = parse_log(LOG_WITH_STATION)
        out_data = parse_output(REPORT_PARTIAL_STATION)
        results = run_checks(MINIMAL_CONFIG, log_data, out_data, None, None)
        fails = results.by_level("FAIL")
        fail_ids = [cid for cid, _ in fails]
        fail_msgs = [msg for cid, msg in fails if cid == "1.3"]
        # Check 1.3 validates output station values and fails on "Unavailable"
        assert len(fail_msgs) == 1, f"Expected exactly 1 fail for 1.3, got: {fail_msgs}"
        assert "current_monthly_rainfall" in fail_msgs[0], f"Expected current_monthly_rainfall flagged, got: {fail_msgs[0]}"
        # avg_temp_today and avg_monthly_rainfall should be fine (not in fail_msgs)
        for msg in fail_msgs:
            assert "avg_temp_today" not in msg
            assert "avg_monthly_rainfall" not in msg
        # 3.2 also fires for Unavailable in output
        assert "3.2" in fail_ids, f"Check 3.2 should fail for 'Unavailable' in output, got: {fail_ids}"


# -----------------------------------------------------------------------
# v1.0.111: Check 4.3 frontmatter category count regression fixtures
# -----------------------------------------------------------------------

REPORT_EMPTY_CAT_VALID = """\
---
title: Daily Brief
date: 2026-08-06
time_generated: 2026-08-06T01:00:00Z
status: active
content_age_window: 48
story_count_total: 1
categories: 2
tags:
  - test
---

## Weather Forecast

**3 Day forecast for 77316:**

| Tuesday | Sunny | Clear | 95°F | 75°F | 20% | 10 mph SW |
| Tonight | Clear | Clear | 85°F | 70°F | 10% | 5 mph S |
| Wednesday | Partly Cloudy | Partly Cloudy | 92°F | 73°F | 30% | 15 mph SW |

| Climate Normal High for today 77316 | 93°F |
| Average Monthly rainfall for 77316 | 3.75 Inches |
| Current Monthly rainfall for 77316 | 2.10 Inches |

| Where | Today | 1 Week Ago | 30 Days ago |
| --- | --- | --- | --- |
| Lake Conroe | 85.2% | 84.1% | 80.5% |
| Lake Houston | 78.9% | 77.5% | 75.2% |

## Populated Category (1 stories)

1. [A Story](https://example.com/1)
   A good summary with enough detail.
*Originally published on:* Aug 6, 2026

[[#test]]

## Empty Category
_No stories found._
"""

REPORT_EMPTY_CAT_MISMATCH = """\
---
title: Daily Brief
date: 2026-08-06
time_generated: 2026-08-06T01:00:00Z
status: active
content_age_window: 48
story_count_total: 1
categories: 1
tags:
  - test
---

## Weather Forecast

**3 Day forecast for 77316:**

| Tuesday | Sunny | Clear | 95°F | 75°F | 20% | 10 mph SW |
| Tonight | Clear | Clear | 85°F | 70°F | 10% | 5 mph S |
| Wednesday | Partly Cloudy | Partly Cloudy | 92°F | 73°F | 30% | 15 mph SW |

| Climate Normal High for today 77316 | 93°F |
| Average Monthly rainfall for 77316 | 3.75 Inches |
| Current Monthly rainfall for 77316 | 2.10 Inches |

| Where | Today | 1 Week Ago | 30 Days ago |
| --- | --- | --- | --- |
| Lake Conroe | 85.2% | 84.1% | 80.5% |
| Lake Houston | 78.9% | 77.5% | 75.2% |

## Populated Category (1 stories)

1. [A Story](https://example.com/1)
   A good summary with enough detail.
*Originally published on:* Aug 6, 2026

[[#test]]

## Empty Category
_No stories found._
"""


LOG_FOR_43_TEST = """\
[2026-08-06 01:05:30] Weather OK -- 3 forecast periods | 1 station record | 11 lake sources
[2026-08-06 01:05:30] [fetch_weather] Station data complete: avg_temp_today=93°F avg_monthly_rainfall=3.77 Inches current_monthly_rainfall=2.10 Inches
[2026-08-06 01:05:30] Phase 1 completed in 5.23s
[2026-08-06 01:05:35] Phase 2 completed in 3.45s
[2026-08-06 01:06:35] Phase 3 completed in 54.71s
[2026-08-06 01:06:35] Phase 4 completed in 0.19s
"""


class TestCheck43FrontmatterCategoryCount:
    """v1.0.111: Frontmatter categories must match rendered section headers, including empty."""

    def test_check43_passes_count_matches_headers(self):
        """Frontmatter categories: 2, two non-weather headers rendered → 4.3 should pass."""
        log_data = parse_log(LOG_FOR_43_TEST)
        out_data = parse_output(REPORT_EMPTY_CAT_VALID)
        results = run_checks(MINIMAL_CONFIG, log_data, out_data, None, None)
        fail_ids = [cid for cid, _ in results.by_level("FAIL")]
        assert "4.3" not in fail_ids, f"Check 4.3 should pass when count matches headers, got fails: {results.by_level('FAIL')}"

    def test_check43_fails_count_mismatch(self):
        """Frontmatter categories: 1, but two non-weather headers rendered → 4.3 should fail."""
        log_data = parse_log(LOG_FOR_43_TEST)
        out_data = parse_output(REPORT_EMPTY_CAT_MISMATCH)
        results = run_checks(MINIMAL_CONFIG, log_data, out_data, None, None)
        fail_ids = [cid for cid, _ in results.by_level("FAIL")]
        assert "4.3" in fail_ids, f"Check 4.3 should fail for count mismatch, got fails: {fail_ids}"

