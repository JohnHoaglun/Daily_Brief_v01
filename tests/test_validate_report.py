"""
Unit tests for daily_brief/validation.py -- report-level validation.
"""
import os
import re
import tempfile
import datetime
from unittest import TestCase, mock

from daily_brief.validation import (
    _parse_frontmatter,
    validate_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_report():
    frontmatter = (
        "---\n"
        "title: Daily Brief\n"
        "date: 2026-07-29\n"
        "time_generated: 2026-07-29T12:00:00Z\n"
        "story_count_total: 10\n"
        "categories: 2\n"
        "tags:\n"
        "  - daily-brief\n"
        "  - news\n"
        "---\n"
    )
    body = "# Daily Brief -- July 29, 2026\n\n"
    body += "## Weather Forecast 77316\n\n"
    body += "| Day | High | Low | Precip | Wind |\n"
    body += "|-----|------|-----|--------|------|\n"
    for day, h, lo, p, w in [("Mon", "85", "68", "0%", "5"), ("Tue", "80", "65", "60%", "10"), ("Wed", "82", "66", "10%", "8"), ("Thu", "84", "67", "0%", "6"), ("Fri", "86", "69", "20%", "7")]:
        body += f"| {day} | {h}   | {lo}  | {p}    | {w}    |\n"
    body += "\n## World News (10 stories)\n\n"
    for i in range(1, 11):
        body += (
            f"{i}. [This Summary Story {i}](https://example.com/story{i})\n"
            f"This is a summary of story {i}. It contains enough detail to be informative.\n"
        )
    body += "\n---\n\n\n"
    body += "x" * (5 * 1024 - len(frontmatter + body) + 100)
    return frontmatter + body


def _write(path, content):
    fh, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fh, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _rm(path):
    if os.path.exists(path):
        os.unlink(path)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TestReturnType(TestCase):
    def test_returns_bool_and_list(self):
        p = _write(None, _valid_report())
        try:
            result = validate_report(p)
            assert isinstance(result, tuple) and len(result) == 2
            passed, issues = result
            assert isinstance(passed, bool)
            assert isinstance(issues, list)
            assert all(isinstance(i, str) for i in issues)
        finally:
            _rm(p)


# ---------------------------------------------------------------------------
# Valid report
# ---------------------------------------------------------------------------

class TestValidReport(TestCase):
    def test_valid_report_passes(self):
        p = _write(None, _valid_report())
        try:
            passed, issues = validate_report(p)
            assert passed
            report_issues = [i for i in issues if "[REPORT-" in i]
            assert report_issues == [], f"Unexpected report issues: {report_issues}"
        finally:
            _rm(p)


# ---------------------------------------------------------------------------
# Report-level checks (parametrized matrix)
# ---------------------------------------------------------------------------

class TestReportChecks(TestCase):
    """One parametrized test for all report-level invalidation paths."""

    def test_missing_frontmatter_fields(self):
        """All 6 required fields each trigger REPORT-1 when absent."""
        for field in ["title", "date", "time_generated", "story_count_total", "categories", "tags"]:
            content = _valid_report()
            line = f"{field}:"
            if line in content:
                content = content.replace(line, "", 1)
            p = _write(None, content)
            try:
                _, issues = validate_report(p)
                r1 = [i for i in issues if "[REPORT-1]" in i]
                assert any(field in i for i in r1), f"Missing [{field}] -> no REPORT-1: {r1}"
            finally:
                _rm(p)

    def test_weather_section_checks(self):
        """REPORT-2 fires when weather section missing or has <3 forecast rows."""
        # Missing section -- use a name without "weather" or "forecast" substring
        content = _valid_report()
        content = content.replace("## Weather Forecast 77316", "## General Info")
        p = _write(None, content)
        try:
            _, issues = validate_report(p)
            assert any("[REPORT-2]" in i for i in issues), f"Missing weather section: {issues}"
        finally:
            _rm(p)

        # Too few rows - drop 4 of 5 data rows
        content = _valid_report()
        lines = content.split("\n")
        new_lines = []
        data_rows = 0
        for line in lines:
            s = line.strip()
            if s.startswith("|") and not all(c == "-" for c in s.replace("|", "").replace(" ", "")):
                data_rows += 1
                if data_rows > 1:
                    continue
            new_lines.append(line)
        content = "\n".join(new_lines)
        p2 = _write(None, content)
        try:
            _, issues = validate_report(p2)
            assert any("[REPORT-2]" in i for i in issues), f"Too few rows: {issues}"
        finally:
            _rm(p2)

    def test_fallback_string_checks(self):
        """REPORT-3 for 'Dynamic', REPORT-4 for 'Unavailable'."""
        for marker, code in [("Dynamic", "REPORT-3"), ("Unavailable", "REPORT-4")]:
            content = _valid_report() + f"\n\nSome {marker} text.\n"
            p = _write(None, content)
            try:
                _, issues = validate_report(p)
                assert any(f"[{code}]" in i for i in issues), f"Expected {code} for '{marker}'"
            finally:
                _rm(p)

    def test_story_count_plausibility(self):
        """REPORT-5 fires for 0 and out-of-range counts."""
        for bad_count in [0, 999]:
            content = _valid_report()
            content = content.replace("story_count_total: 10", f"story_count_total: {bad_count}")
            p = _write(None, content)
            try:
                _, issues = validate_report(p)
                assert any("[REPORT-5]" in i for i in issues), f"Expected REPORT-5 for count={bad_count}"
            finally:
                _rm(p)

    def test_duplicate_url(self):
        """REPORT-6 when same URL appears in two story links."""
        content = _valid_report()
        content = content.replace(
            "[This Summary Story 2](https://example.com/story2)",
            "[Dup](https://example.com/story1)"
        )
        p = _write(None, content)
        try:
            _, issues = validate_report(p)
            assert any("[REPORT-6]" in i for i in issues)
        finally:
            _rm(p)

    def test_file_too_small(self):
        """REPORT-7 when file is under 5KB."""
        p = _write(None, "# Small\nhello\n")
        try:
            _, issues = validate_report(p)
            assert any("[REPORT-7]" in i for i in issues)
        finally:
            _rm(p)

    def test_file_too_large_mocked(self):
        """REPORT-7 when file exceeds 10MB (mocked)."""
        p = _write(None, _valid_report())
        try:
            with mock.patch("daily_brief.validation.os.path.getsize", return_value=11 * 1024 * 1024):
                _, issues = validate_report(p)
                assert any("[REPORT-7]" in i for i in issues)
        finally:
            _rm(p)


# ---------------------------------------------------------------------------
# Per-story checks
# ---------------------------------------------------------------------------

PAD = "x" * 6000

def _story_report(stories_block, count):
    return (
        "---\ntitle: Daily Brief\ndate: 2026-07-29\ntime_generated: 2026-07-29T12:00:00Z\n"
        f"story_count_total: {count}\ncategories: 1\ntags:\n  - test\n---\n"
        "# Daily Brief\n\n"
        "## Weather Forecast 77316\n\n"
        "| Day | High | Low | Precip | Wind |\n|-----|------|-----|--------|------|\n"
        "| Mon | 85  | 68  | 0%    | 5    |\n| Tue | 80  | 65  | 60%   | 10   |\n"
        "| Wed | 82  | 66  | 10%   | 8    |\n\n"
        f"## World News ({count} stories)\n\n"
        f"{stories_block}\n{PAD}\n"
    )


class TestPerStory(TestCase):
    def test_summary_quality_failures(self):
        """Empty summary, headline repeat, too short, topic mismatch, [Headline] fallback — all detected."""
        # Empty summary (only tag line after title, no real summary text)
        stories = ""
        for i in range(1, 11):
            stories += f"{i}. [Good {i}](https://example.com/g{i})\nThis is a good summary with enough detail.\n"
        stories += "11. [Empty](https://example.com/empty)\n[[tag1]]\n\n## Padding\n\n"
        content = _story_report(stories, 11)
        p = _write(None, content)
        try:
            _, issues = validate_report(p)
            assert any("Empty summary" in i for i in issues)
        finally:
            _rm(p)

        # Headline repeat
        content = _story_report(
            "1. [Breaking News About the Weather](https://example.com/r)\nBreaking News About the Weather.\n",
            1
        )
        p = _write(None, content)
        try:
            _, issues = validate_report(p)
            assert any("repeats headline" in i for i in issues)
        finally:
            _rm(p)

        # Too short
        content = _story_report(
            "1. [Short Story](https://example.com/s)\nOnly one sentence.\n",
            1
        )
        p = _write(None, content)
        try:
            _, issues = validate_report(p)
            assert any("Too short" in i for i in issues)
        finally:
            _rm(p)

        # Topic mismatch
        stories = "1. [Hurricane Damages Texas Coast](https://example.com/t)\n"
        stories += "Unrelated summary about cooking recipes. Nothing about weather.\n"
        content = _story_report(stories, 1)
        p = _write(None, content)
        try:
            _, issues = validate_report(p)
            assert any("Topic mismatch" in i for i in issues)
        finally:
            _rm(p)

        # [Headline] fallback marker
        stories = "1. [Bad Story](https://example.com/h)\n[Headline] The headline was the only thing available. No other data could be retrieved.\n"
        stories += "2. [Good Story](https://example.com/g)\nThis is a good summary with enough detail.\n"
        content = _story_report(stories, 2)
        p = _write(None, content)
        try:
            _, issues = validate_report(p)
            assert any("Fallback marker" in i for i in issues), f"Fallback not detected: {issues}"
        finally:
            _rm(p)

    def test_auto_fallback_accepted(self):
        """[Auto] prefix is NOT flagged as a failure."""
        stories = "1. [Auto Story](https://example.com/a)\n[Auto] Auto generated summary. Some detail included.\n"
        content = _story_report(stories, 1)
        p = _write(None, content)
        try:
            _, issues = validate_report(p)
            assert not any("Fallback marker" in i for i in issues)
        finally:
            _rm(p)


# ---------------------------------------------------------------------------
# _parse_frontmatter edge cases
# ---------------------------------------------------------------------------

class TestParseFrontmatter(TestCase):
    def test_few_parts(self):
        meta, body = _parse_frontmatter("---\nfoo: bar")
        assert meta == {}
        assert body == "---\nfoo: bar"

    def test_no_delimiter(self):
        meta, body = _parse_frontmatter("just plain text")
        assert meta == {}
        assert body == "just plain text"

    def test_valid(self):
        meta, body = _parse_frontmatter("---\ntitle: Test\ndate: 2026-01-01\n---\nbody text")
        assert meta["title"] == "Test"
        assert meta["date"] == datetime.date(2026, 1, 1)
        assert body == "body text"


# ---------------------------------------------------------------------------
# file errors
# ---------------------------------------------------------------------------

class TestFileErrors(TestCase):
    def test_nonexistent_file(self):
        passed, issues = validate_report("/nonexistent/path/to/report.md")
        assert passed is False
        assert len(issues) > 0

    def test_read_error(self):
        p = _write(None, "---\ntitle: T\n---")
        try:
            with mock.patch("builtins.open", side_effect=PermissionError("denied")):
                passed, issues = validate_report(p)
            assert passed is False
            assert any("Cannot read file" in i for i in issues)
        finally:
            _rm(p)


# ---------------------------------------------------------------------------
# Issue format
# ---------------------------------------------------------------------------

class TestIssueFormat(TestCase):
    def test_all_report_issues_prefixed(self):
        content = _valid_report()
        for strip in ["title:", "## Weather Forecast 77316", "story_count_total: 10"]:
            content = content.replace(strip, "", 1)
        content += "\nDynamic\nUnavailable\n"
        p = _write(None, content)
        try:
            _, issues = validate_report(p)
            report_issues = [i for i in issues if "[REPORT-" in i]
            assert len(report_issues) >= 3
            for issue in report_issues:
                assert re.search(r"\[REPORT-\d+\]", issue), f"No prefix: {issue}"
        finally:
            _rm(p)
