"""
Unit tests for src/daily_brief/validation.py — report-level validation.

Tests 8 report-level checks + existing per-story check regression.
"""
import os
import sys
import tempfile
from unittest import TestCase, mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from daily_brief.validation import validate_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_report():
    """Return a synthetically valid report markdown string (well over 5KB)."""
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

    # Weather section with 5 forecast rows
    body += "## Weather Forecast 77316\n\n"
    body += "| Day | High | Low | Precip | Wind |\n"
    body += "|-----|------|-----|--------|------|\n"
    body += "| Mon | 85   | 68  | 0%     | 5    |\n"
    body += "| Tue | 80   | 65  | 60%    | 10   |\n"
    body += "| Wed | 82   | 66  | 10%    | 8    |\n"
    body += "| Thu | 84   | 67  | 0%     | 6    |\n"
    body += "| Fri | 86   | 69  | 20%    | 7    |\n\n"

    # Category section with 10 unique URLs — titles must contain words found in summaries
    body += "## World News (10 stories)\n\n"
    for i in range(1, 11):
        body += (
            f"{i}. [This Summary Story {i}](https://example.com/story{i})\n"
            f"This is a summary of story {i}. It contains enough detail to be informative.\n"
        )

    # Separator to prevent padding from bleeding into last story's summary
    body += "\n---\n"

    # Pad to over 5KB (pad in a non-story section after separator)
    body += "\n\n" + "x" * (5 * 1024 - len(frontmatter + body) + 100)

    return frontmatter + body


def _write_report(content):
    """Write content to a temp file and return its path. Caller must delete."""
    fh, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fh, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _cleanup(path):
    if os.path.exists(path):
        os.unlink(path)


# ---------------------------------------------------------------------------
# Report returns correct types
# ---------------------------------------------------------------------------

class TestReturnType(TestCase):
    """validate_report returns (bool, list[str])."""

    def test_return_type_tuple(self):
        path = _write_report(_valid_report())
        try:
            result = validate_report(path)
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 2)
        finally:
            _cleanup(path)

    def test_return_bool_and_list(self):
        path = _write_report(_valid_report())
        try:
            passed, issues = validate_report(path)
            self.assertIsInstance(passed, bool)
            self.assertIsInstance(issues, list)
        finally:
            _cleanup(path)

    def test_issue_strings_are_strings(self):
        path = _write_report("# No valid content here\n" + "x" * 6000)
        try:
            _, issues = validate_report(path)
            for issue in issues:
                self.assertIsInstance(issue, str)
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# Valid report passes all report-level checks
# ---------------------------------------------------------------------------

class TestValidReportPasses(TestCase):
    """A well-formed report has no [REPORT-N] issues."""

    def test_valid_report_no_report_issues(self):
        path = _write_report(_valid_report())
        try:
            passed, issues = validate_report(path)
            report_issues = [i for i in issues if "[REPORT-" in i]
            self.assertEqual(report_issues, [], f"Expected no report issues, got: {report_issues}")
        finally:
            _cleanup(path)

    def test_valid_report_passes(self):
        path = _write_report(_valid_report())
        try:
            passed, _ = validate_report(path)
            self.assertTrue(passed)
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# REPORT-1: Frontmatter required fields
# ---------------------------------------------------------------------------

class TestFrontmatter(TestCase):
    """REPORT-1: All required frontmatter fields present."""

    def _missing_field(self, field):
        content = _valid_report()
        for fm_field in ["title", "date", "time_generated", "story_count_total", "categories", "tags"]:
            if fm_field == field:
                line = f"{fm_field}:"
                if line in content:
                    content = content.replace(line, "", 1)
                    break
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report1 = [i for i in issues if "[REPORT-1]" in i]
            self.assertTrue(any(field in i for i in report1), f"Expected issue for missing '{field}': {report1}")
        finally:
            _cleanup(path)

    def test_missing_title(self):
        self._missing_field("title")

    def test_missing_date(self):
        self._missing_field("date")

    def test_missing_time_generated(self):
        self._missing_field("time_generated")

    def test_missing_story_count_total(self):
        self._missing_field("story_count_total")

    def test_missing_categories(self):
        self._missing_field("categories")

    def test_missing_tags(self):
        self._missing_field("tags")

    def test_issue_has_report_1_prefix(self):
        content = _valid_report()
        content = content.replace("title:", "", 1)
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report1 = [i for i in issues if "[REPORT-1]" in i]
            self.assertGreater(len(report1), 0)
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# REPORT-2: Weather section
# ---------------------------------------------------------------------------

class TestWeatherSection(TestCase):
    """REPORT-2: Weather section with >=3 forecast rows."""

    def test_missing_weather_section(self):
        content = _valid_report()
        content = content.replace("## Weather Forecast 77316", "## Some Other Section")
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report2 = [i for i in issues if "[REPORT-2]" in i]
            self.assertGreater(len(report2), 0)
        finally:
            _cleanup(path)

    def test_few_forecast_rows(self):
        content = _valid_report()
        # Remove forecast data rows, keeping only header + separator
        lines = content.split("\n")
        new_lines = []
        data_rows = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and not all(c == "-" for c in stripped.replace("|", "").replace(" ", "")):
                data_rows += 1
                if data_rows > 1:
                    continue  # Skip after first data row
            new_lines.append(line)
        content = "\n".join(new_lines)
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report2 = [i for i in issues if "[REPORT-2]" in i]
            self.assertGreater(len(report2), 0)
        finally:
            _cleanup(path)

    def test_valid_weather_passes(self):
        content = _valid_report()
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report2 = [i for i in issues if "[REPORT-2]" in i]
            self.assertEqual(report2, [])
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# REPORT-3: No "Dynamic" string
# ---------------------------------------------------------------------------

class TestDynamicString(TestCase):
    """REPORT-3: Weather fallback 'Dynamic' not in body."""

    def test_dynamic_present_fails(self):
        content = _valid_report()
        content += "\n\nDynamic weather data unavailable.\n"
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report3 = [i for i in issues if "[REPORT-3]" in i]
            self.assertGreater(len(report3), 0)
        finally:
            _cleanup(path)

    def test_dynamic_absent_passes(self):
        content = _valid_report()
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report3 = [i for i in issues if "[REPORT-3]" in i]
            self.assertEqual(report3, [])
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# REPORT-4: No "Unavailable" string
# ---------------------------------------------------------------------------

class TestUnavailableString(TestCase):
    """REPORT-4: Data fallback 'Unavailable' not in body."""

    def test_unavailable_present_fails(self):
        content = _valid_report()
        content += "\n\nData Unavailable at this time.\n"
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report4 = [i for i in issues if "[REPORT-4]" in i]
            self.assertGreater(len(report4), 0)
        finally:
            _cleanup(path)

    def test_unavailable_absent_passes(self):
        content = _valid_report()
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report4 = [i for i in issues if "[REPORT-4]" in i]
            self.assertEqual(report4, [])
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# REPORT-5: Story count plausible
# ---------------------------------------------------------------------------

class TestStoryCount(TestCase):
    """REPORT-5: story_count_total in plausible range."""

    def test_story_count_zero(self):
        content = _valid_report()
        content = content.replace("story_count_total: 10", "story_count_total: 0")
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report5 = [i for i in issues if "[REPORT-5]" in i]
            self.assertGreater(len(report5), 0)
        finally:
            _cleanup(path)

    def test_story_count_way_over(self):
        content = _valid_report()
        content = content.replace("story_count_total: 10", "story_count_total: 999")
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report5 = [i for i in issues if "[REPORT-5]" in i]
            self.assertGreater(len(report5), 0)
        finally:
            _cleanup(path)

    def test_story_count_normal_passes(self):
        content = _valid_report()
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report5 = [i for i in issues if "[REPORT-5]" in i]
            self.assertEqual(report5, [])
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# REPORT-7: Duplicate URLs
# ---------------------------------------------------------------------------

class TestDuplicateURLs(TestCase):
    """REPORT-7: No duplicate markdown URLs."""

    def test_duplicate_urls_detected(self):
        content = _valid_report()
        content = content.replace(
            "[This Summary Story 2](https://example.com/story2)",
            "[This Summary Story 2 Dup](https://example.com/story1)"
        )
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report7 = [i for i in issues if "[REPORT-7]" in i]
            self.assertGreater(len(report7), 0)
        finally:
            _cleanup(path)

    def test_no_duplicates_passes(self):
        content = _valid_report()
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report7 = [i for i in issues if "[REPORT-7]" in i]
            self.assertEqual(report7, [])
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# REPORT-8: File size reasonable
# ---------------------------------------------------------------------------

class TestFileSize(TestCase):
    """REPORT-8: File size between 5KB and 10MB."""

    def test_file_too_small(self):
        path = _write_report("# Small report\njust a few words\n")
        try:
            _, issues = validate_report(path)
            report8 = [i for i in issues if "[REPORT-8]" in i]
            self.assertGreater(len(report8), 0)
        finally:
            _cleanup(path)

    def test_file_too_large_mocked(self):
        content = _valid_report()
        path = _write_report(content)
        try:
            with mock.patch("daily_brief.validation.os.path.getsize", return_value=11 * 1024 * 1024):
                _, issues = validate_report(path)
                report8 = [i for i in issues if "[REPORT-8]" in i]
                self.assertGreater(len(report8), 0)
        finally:
            _cleanup(path)

    def test_normal_file_size_passes(self):
        content = _valid_report()
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report8 = [i for i in issues if "[REPORT-8]" in i]
            self.assertEqual(report8, [])
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# Per-story checks regression
# ---------------------------------------------------------------------------

class TestPerStoryRegression(TestCase):
    """Existing per-story checks must not regress."""

    def test_empty_summary_detected(self):
        # Test that a story with a title followed only by filtered lines
        # (e.g. [[tags]]) triggers the empty summary check.
        stories = ""
        for i in range(1, 11):
            stories += (
                f"{i}. [This Summary Story {i}](https://example.com/good{i})\n"
                f"This is a good summary with detail in this story. It contains many words.\n"
            )
        # Story whose only "summary" content is a tag line ([[...]]), which is filtered out
        stories += (
            "11. [This Empty Summary](https://example.com/empty)\n"
            "[[tag1]]\n"
        )

        content = (
            "---\n"
            "title: Daily Brief\n"
            "date: 2026-07-29\n"
            "time_generated: 2026-07-29T12:00:00Z\n"
            "story_count_total: 11\n"
            "categories: 1\n"
            "tags:\n"
            "  - test\n"
            "---\n"
            f"# Daily Brief\n\n"
            f"## Weather Forecast 77316\n\n"
            f"| Day | High | Low | Precip | Wind |\n"
            f"|-----|------|-----|--------|------|\n"
            f"| Mon | 85  | 68  | 0%    | 5    |\n"
            f"| Tue | 80  | 65  | 60%   | 10   |\n"
            f"| Wed | 82  | 66  | 10%   | 8    |\n\n"
            f"## World News (11 stories)\n\n"
            f"{stories}"
            f"## Padding\n\n"
            f"{'x' * 6000}\n"
        )
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            empty_issues = [i for i in issues if "Empty summary" in i]
            self.assertGreater(len(empty_issues), 0)
        finally:
            _cleanup(path)

    def test_headline_repeat_detected(self):
        story_title = "Breaking News About the Weather"
        content = (
            "---\n"
            "title: Daily Brief\n"
            "date: 2026-07-29\n"
            "time_generated: 2026-07-29T12:00:00Z\n"
            "story_count_total: 1\n"
            "categories: 1\n"
            "tags:\n"
            "  - test\n"
            "---\n"
            f"# Daily Brief\n\n"
            f"## Weather Forecast 77316\n\n"
            f"| Day | High | Low | Precip | Wind |\n"
            f"|-----|------|-----|--------|------|\n"
            f"| Mon | 85  | 68  | 0%    | 5    |\n"
            f"| Tue | 80  | 65  | 60%   | 10   |\n"
            f"| Wed | 82  | 66  | 10%   | 8    |\n\n"
            f"## World News (1 stories)\n\n"
            f"1. [{story_title}](https://example.com/repeat)\n"
            f"Breaking News About the Weather.\n\n"
            f"{'x' * 6000}\n"
        )
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            repeat_issues = [i for i in issues if "repeats headline" in i]
            self.assertGreater(len(repeat_issues), 0)
        finally:
            _cleanup(path)

    def test_too_short_summary_detected(self):
        content = (
            "---\n"
            "title: Daily Brief\n"
            "date: 2026-07-29\n"
            "time_generated: 2026-07-29T12:00:00Z\n"
            "story_count_total: 1\n"
            "categories: 1\n"
            "tags:\n"
            "  - test\n"
            "---\n"
            f"# Daily Brief\n\n"
            f"## Weather Forecast 77316\n\n"
            f"| Day | High | Low | Precip | Wind |\n"
            f"|-----|------|-----|--------|------|\n"
            f"| Mon | 85  | 68  | 0%    | 5    |\n"
            f"| Tue | 80  | 65  | 60%   | 10   |\n"
            f"| Wed | 82  | 66  | 10%   | 8    |\n\n"
            f"## World News (1 stories)\n\n"
            f"1. [Short Story Title](https://example.com/short)\n"
            f"Only one sentence here.\n\n"
            f"{'x' * 6000}\n"
        )
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            short_issues = [i for i in issues if "Too short" in i]
            self.assertGreater(len(short_issues), 0)
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# Issue string format
# ---------------------------------------------------------------------------

class TestIssueFormat(TestCase):
    """Issue strings follow the [REPORT-N] format."""

    def test_all_report_issues_have_prefix(self):
        content = _valid_report()
        content = content.replace("title:", "", 1)
        content = content.replace("## Weather Forecast 77316", "## Some Other Section")
        content += "\nDynamic\n"
        content += "\nUnavailable\n"
        content = content.replace("story_count_total: 10", "story_count_total: 0")
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            report_issues = [i for i in issues if "[REPORT-" in i]
            self.assertGreater(len(report_issues), 3, "Expected multiple report issues")
            for issue in report_issues:
                self.assertRegex(issue, r"\[REPORT-\d+\]", f"Issue missing [REPORT-N] prefix: {issue}")
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# File not found
# ---------------------------------------------------------------------------

class TestFileNotFound(TestCase):
    """Validate handles missing files gracefully."""

    def test_nonexistent_file(self):
        passed, issues = validate_report("/nonexistent/path/to/report.md")
        self.assertFalse(passed)
        self.assertGreater(len(issues), 0)
