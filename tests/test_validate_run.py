"""Tests for daily_brief/validation_harness.py - log/output parsing + check execution."""

from daily_brief.validation_harness import parse_log, parse_output, run_checks

# ---------------------------------------------------------------------------
# Fixtures -- factory to build report strings from overrides
# ---------------------------------------------------------------------------


def _report(fm_overrides=None, body_overrides=None):
    fm = {
        "title": "Daily Brief",
        "date": "2026-08-04",
        "time_generated": "2026-08-04T01:06:35Z",
        "status": "active",
        "content_age_window": 48,
        "story_count_total": 1,
        "categories": 1,
        "tags": ["test"],
    }
    if fm_overrides:
        fm.update(fm_overrides)
    fm_lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}:")
            for item in v:
                fm_lines.append(f"  - {item}")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")

    body = "\n".join(fm_lines) + "\n\n"
    body += "## Weather Forecast\n\n"
    forecast = body_overrides and body_overrides.get("forecast")
    if forecast is not None:
        body += forecast
    else:
        body += "**3 Day forecast for 77316:**\n\n"
        rows = [
            ("Tuesday", "Partly Cloudy", "Clear", "95\u00b0F", "75\u00b0F", "20%", "10 mph SW"),
            ("Tonight", "Clear", "Clear", "85\u00b0F", "70\u00b0F", "10%", "5 mph S"),
            (
                "Wednesday",
                "Partly Cloudy",
                "Partly Cloudy",
                "92\u00b0F",
                "73\u00b0F",
                "30%",
                "15 mph SW",
            ),
        ]
        for row in rows:
            body += "| " + " | ".join(row) + " |\n"
        body += "\n"

    station = body_overrides and body_overrides.get("station")
    if station is not None:
        body += station
    else:
        for label, val in [
            ("Climate Normal High for today 77316", "93\u00b0F"),
            ("Average Monthly rainfall for 77316", "3.75 Inches"),
            ("Current Monthly rainfall for 77316", "2.10 Inches"),
        ]:
            body += f"| {label} | {val} |\n"
        body += "\n"

    lakes = body_overrides and body_overrides.get("lakes")
    if lakes is not None:
        body += lakes
    else:
        body += "|\n| Where | Today | 1 Week Ago | 30 Days ago |\n"
        body += "| --- | --- | --- | --- |\n"
        body += "| Lake Conroe | 85.2% | 84.1% | 80.5% |\n"
        body += "| Lake Houston | 78.9% | 77.5% | 75.2% |\n\n"

    stories = body_overrides and body_overrides.get("stories")
    if stories is not None:
        body += stories
    else:
        body += "## World News (1 stories)\n\n"
        body += "1. [Test Story](https://example.com/1)\n"
        body += "   Test summary sentence.\n"
        body += "*Originally published on:* Aug 4, 2026\n\n"
        body += "[[#world]]\n"

    return body


def _log(has_station=True, phases=None):
    parts = []
    parts.append(
        "[2026-08-04 01:05:30] Weather OK -- 3 forecast periods | 1 station record | 11 lake sources\n"
    )
    if has_station:
        parts.append(
            "[2026-08-04 01:05:30] [fetch_weather] Station data complete: avg_temp_today=93\u00b0F avg_monthly_rainfall=3.77 Inches current_monthly_rainfall=2.10 Inches\n"
        )
    if phases is None:
        phases = {1: 5.23, 2: 3.45, 3: 54.71, 4: 0.19}
    for pk, pv in sorted(phases.items()):
        parts.append(f"[2026-08-04 01:05:3{pk}] Phase {pk} completed in {pv}s\n")
    return "".join(parts)


def _harness_log():
    return (
        "[2026-08-06 01:05:30] Weather OK -- 3 forecast periods | 1 station record | 11 lake sources\n"
        "[2026-08-06 01:05:30] [fetch_weather] Station data complete: avg_temp_today=93\u00b0F avg_monthly_rainfall=3.77 Inches current_monthly_rainfall=2.10 Inches\n"
        "[2026-08-06 01:05:30] Phase 1 completed in 5.23s\n"
        "[2026-08-06 01:05:35] Phase 2 completed in 3.45s\n"
        "[2026-08-06 01:06:35] Phase 3 completed in 54.71s\n"
        "[2026-08-06 01:06:35] Phase 4 completed in 0.19s\n"
    )


CFG = {
    "weather": {"lake_urls": {"Lake Conroe": "http://x", "Lake Houston": "http://x"}},
    "directories": {"news_dir": "/fake/news/dir"},
}


# ---------------------------------------------------------------------------
# parse_log
# ---------------------------------------------------------------------------


class TestParseLog:
    def test_full_parse(self):
        """Parse forecast periods, station, phase timings from a realistic log."""
        data = parse_log(_log())
        assert data["forecast_periods"] == 3
        assert data["station_complete"] is not None
        assert len(data["station_complete"]) == 3
        assert data["phase_timings"][1] == 5.23
        assert data["phase_timings"][2] == 3.45
        assert data["phase_timings"][3] == 54.71
        assert data["phase_timings"][4] == 0.19

    def test_no_station(self):
        data = parse_log(_log(has_station=False))
        assert data["station_complete"] is None


# ---------------------------------------------------------------------------
# parse_output
# ---------------------------------------------------------------------------


class TestParseOutput:
    def test_full_parse(self):
        """Parse forecast rows, station values, lakes from a valid report."""
        data = parse_output(_report())
        assert data["forecast_row_count"] == 3
        station = data["station_values"]
        assert station["avg_temp_today"] == "93\u00b0F"
        assert station["avg_monthly_rainfall"] == "3.75 Inches"
        assert station["current_monthly_rainfall"] == "2.10 Inches"
        assert len(data["lake_rows"]) >= 2
        assert "Conroe" in data["lake_rows"]
        assert "Houston" in data["lake_rows"]

    def test_no_forecast(self):
        data = parse_output(_report(body_overrides={"forecast": ""}))
        assert data["forecast_row_count"] == 0

    def test_unavailable_station(self):
        station_text = (
            "| Climate Normal High for today 77316 | Unavailable |\n"
            "| Average Monthly rainfall for 77316 | Unavailable |\n"
            "| Current Monthly rainfall for 77316 | Unavailable |\n\n"
        )
        data = parse_output(_report(body_overrides={"station": station_text}))
        for v in data["station_values"].values():
            assert v == "Unavailable"


# ---------------------------------------------------------------------------
# run_checks
# ---------------------------------------------------------------------------


class TestRunChecks:
    def _run(self, log_text=None, report_text=None):
        log_data = parse_log(log_text or _log())
        out_data = parse_output(report_text or _report())
        return run_checks(CFG, log_data, out_data, None, None)

    def test_phase1_pass(self):
        """Valid data: checks 1.2 (forecast rows) and 1.3 (station) pass."""
        results = self._run()
        fail_ids = [cid for cid, _ in results.by_level("FAIL")]
        assert "1.2" not in fail_ids
        assert "1.3" not in fail_ids

    def test_phase1_fail_no_forecast(self):
        """Check 1.2 fails when forecast row count is 0."""
        results = self._run(report_text=_report(body_overrides={"forecast": ""}))
        assert "1.2" in [cid for cid, _ in results.by_level("FAIL")]

    def test_phase1_fail_station_unavailable(self):
        """Check 1.3 fails when station data is all Unavailable."""
        station_text = (
            "| Climate Normal High for today 77316 | Unavailable |\n"
            "| Average Monthly rainfall for 77316 | Unavailable |\n"
            "| Current Monthly rainfall for 77316 | Unavailable |\n\n"
        )
        results = self._run(report_text=_report(body_overrides={"station": station_text}))
        assert "1.3" in [cid for cid, _ in results.by_level("FAIL")]

    def test_partial_station_tolerates_unavailable_rainfall(self):
        """Only current_monthly_rainfall is Unavailable -- 1.3 fires once for that field."""
        station_text = (
            "| Climate Normal High for today 77316 | 93\u00b0F |\n"
            "| Average Monthly rainfall for 77316 | 3.75 Inches |\n"
            "| Current Monthly rainfall for 77316 | Unavailable |\n\n"
        )
        results = self._run(report_text=_report(body_overrides={"station": station_text}))
        fails_13 = [msg for cid, msg in results.by_level("FAIL") if cid == "1.3"]
        assert len(fails_13) == 1
        assert "current_monthly_rainfall" in fails_13[0]
        for msg in fails_13:
            assert "avg_temp_today" not in msg
            assert "avg_monthly_rainfall" not in msg
        assert "3.2" in [cid for cid, _ in results.by_level("FAIL")]


# ---------------------------------------------------------------------------
# Check 4.3: frontmatter category count
# ---------------------------------------------------------------------------


def _report_with_cats(fm_cats, sections):
    fm = {
        "title": "Daily Brief",
        "date": "2026-08-06",
        "time_generated": "2026-08-06T01:00:00Z",
        "status": "active",
        "content_age_window": 48,
        "story_count_total": 1,
        "categories": fm_cats,
        "tags": ["test"],
    }
    fm_lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            fm_lines.append(f"{k}:")
            for item in v:
                fm_lines.append(f"  - {item}")
        else:
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")

    body = "\n".join(fm_lines) + "\n\n"
    body += "## Weather Forecast\n\n"
    body += "**3 Day forecast for 77316:**\n\n"
    for row in [
        ("Tuesday", "Sunny", "Clear", "95\u00b0F", "75\u00b0F", "20%", "10 mph SW"),
        ("Tonight", "Clear", "Clear", "85\u00b0F", "70\u00b0F", "10%", "5 mph S"),
        (
            "Wednesday",
            "Partly Cloudy",
            "Partly Cloudy",
            "92\u00b0F",
            "73\u00b0F",
            "30%",
            "15 mph SW",
        ),
    ]:
        body += "| " + " | ".join(row) + " |\n"
    body += "\n"
    body += "| Climate Normal High for today 77316 | 93\u00b0F |\n"
    body += "| Average Monthly rainfall for 77316 | 3.75 Inches |\n"
    body += "| Current Monthly rainfall for 77316 | 2.10 Inches |\n\n"
    body += "| Where | Today | 1 Week Ago | 30 Days ago |\n"
    body += "| --- | --- | --- | --- |\n"
    body += "| Lake Conroe | 85.2% | 84.1% | 80.5% |\n"
    body += "| Lake Houston | 78.9% | 77.5% | 75.2% |\n\n"
    body += sections
    return body


class TestCheck43FrontmatterCategoryCount:
    """v1.0.111: frontmatter categories must match rendered section headers."""

    def test_43_passes_count_matches(self):
        sections = (
            "## Populated Category (1 stories)\n\n"
            "1. [A Story](https://example.com/1)\n"
            "   A good summary with enough detail.\n"
            "*Originally published on:* Aug 6, 2026\n\n[[#test]]\n\n"
            "## Empty Category\n_No stories found._\n"
        )
        results = run_checks(
            CFG,
            parse_log(_harness_log()),
            parse_output(_report_with_cats(2, sections)),
            None,
            None,
        )
        fail_ids = [cid for cid, _ in results.by_level("FAIL")]
        assert "4.3" not in fail_ids

    def test_43_fails_count_mismatch(self):
        sections = (
            "## Populated Category (1 stories)\n\n"
            "1. [A Story](https://example.com/1)\n"
            "   A good summary with enough detail.\n"
            "*Originally published on:* Aug 6, 2026\n\n[[#test]]\n\n"
            "## Empty Category\n_No stories found._\n"
        )
        results = run_checks(
            CFG,
            parse_log(_harness_log()),
            parse_output(_report_with_cats(1, sections)),
            None,
            None,
        )
        fail_ids = [cid for cid, _ in results.by_level("FAIL")]
        assert "4.3" in fail_ids
