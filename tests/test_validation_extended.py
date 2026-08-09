"""
Extended validation tests — edge cases for frontmatter, story parsing,
and per-story validation logic.
"""
import os
import tempfile
from unittest import TestCase, mock

from daily_brief.validation import (
    _parse_frontmatter,
    validate_report,
)


def _write_report(content):
    fh, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fh, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _cleanup(path):
    if os.path.exists(path):
        os.unlink(path)


PAD = "x" * (5 * 1024)


# ---------------------------------------------------------------------------
# _parse_frontmatter edge cases
# ---------------------------------------------------------------------------

class TestParseFrontmatter(TestCase):
    """_parse_frontmatter edge cases."""

    def test_parse_frontmatter_few_parts(self):
        content = "---\nfoo: bar"
        meta, body = _parse_frontmatter(content)
        self.assertEqual(meta, {})
        self.assertEqual(body, content)

    def test_parse_frontmatter_no_delimiter(self):
        content = "just plain text"
        meta, body = _parse_frontmatter(content)
        self.assertEqual(meta, {})
        self.assertEqual(body, content)

    def test_parse_frontmatter_valid(self):
        import datetime
        content = "---\ntitle: Test\ndate: 2026-01-01\n---\nbody text here"
        meta, body = _parse_frontmatter(content)
        self.assertEqual(meta["title"], "Test")
        self.assertEqual(meta["date"], datetime.date(2026, 1, 1))
        self.assertEqual(body, "body text here")


# ---------------------------------------------------------------------------
# validate_report file read error
# ---------------------------------------------------------------------------

class TestValidateReportFileError(TestCase):
    """validate_report handles file read errors."""

    def test_validate_report_read_error(self):
        path = _write_report("---\ntitle: T\n---")
        try:
            with mock.patch("builtins.open", side_effect=PermissionError("denied")):
                passed, issues = validate_report(path)
            self.assertFalse(passed)
            self.assertTrue(any("Cannot read file" in i for i in issues))
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# Story parsing: empty section, empty block, one-line
# ---------------------------------------------------------------------------

class TestStoryParsingEdgeCases(TestCase):
    """Edge cases in story block parsing."""

    def test_empty_section_text_continue(self):
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
            "# Daily Brief\n\n"
            "\n\n\n"
            "## Weather Forecast 77316\n\n"
            "| Day | High | Low | Precip | Wind |\n"
            "|-----|------|-----|--------|------|\n"
            "| Mon | 85  | 68  | 0%    | 5    |\n"
            "| Tue | 80  | 65  | 60%   | 10   |\n"
            "| Wed | 82  | 66  | 10%   | 8    |\n\n"
            "## World News (1 stories)\n\n"
            "1. [Good Story](https://example.com/1)\nThis is a summary with detail. It has enough content.\n\n"
            f"{PAD}\n"
        )
        path = _write_report(content)
        try:
            passed, issues = validate_report(path)
            no_story_issues = [i for i in issues if "No stories found" in i]
            self.assertEqual(len(no_story_issues), 0)
        finally:
            _cleanup(path)

    def test_empty_story_block_continue(self):
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
            "# Daily Brief\n\n"
            "## Weather Forecast 77316\n\n"
            "| Day | High | Low | Precip | Wind |\n"
            "|-----|------|-----|--------|------|\n"
            "| Mon | 85  | 68  | 0%    | 5    |\n"
            "| Tue | 80  | 65  | 60%   | 10   |\n"
            "| Wed | 82  | 66  | 10%   | 8    |\n\n"
            "## World News (1 stories)\n\n"
            "\n\n1. [Good Story](https://example.com/1)\nThis is a summary with detail. It has enough content.\n\n"
            f"{PAD}\n"
        )
        path = _write_report(content)
        try:
            passed, issues = validate_report(path)
            no_story_issues = [i for i in issues if "No stories found" in i]
            self.assertEqual(len(no_story_issues), 0)
        finally:
            _cleanup(path)

    def test_story_one_line_skip(self):
        content = (
            "---\n"
            "title: Daily Brief\n"
            "date: 2026-07-29\n"
            "time_generated: 2026-07-29T12:00:00Z\n"
            "story_count_total: 2\n"
            "categories: 1\n"
            "tags:\n"
            "  - test\n"
            "---\n"
            "# Daily Brief\n\n"
            "## Weather Forecast 77316\n\n"
            "| Day | High | Low | Precip | Wind |\n"
            "|-----|------|-----|--------|------|\n"
            "| Mon | 85  | 68  | 0%    | 5    |\n"
            "| Tue | 80  | 65  | 60%   | 10   |\n"
            "| Wed | 82  | 66  | 10%   | 8    |\n\n"
            "## World News (2 stories)\n\n"
            "1. [One Liner](https://example.com/1)\n\n"
            "2. [Good Story](https://example.com/2)\nThis is a good summary. It has detail.\n\n"
            f"{PAD}\n"
        )
        path = _write_report(content)
        try:
            passed, issues = validate_report(path)
            no_story_issues = [i for i in issues if "No stories found" in i]
            self.assertEqual(len(no_story_issues), 0)
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# Fallback markers
# ---------------------------------------------------------------------------

class TestFallbackMarkers(TestCase):
    """[Auto] vs [Headline] fallback marker handling."""

    def test_auto_fallback_accepted(self):
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
            "# Daily Brief\n\n"
            "## Weather Forecast 77316\n\n"
            "| Day | High | Low | Precip | Wind |\n"
            "|-----|------|-----|--------|------|\n"
            "| Mon | 85  | 68  | 0%    | 5    |\n"
            "| Tue | 80  | 65  | 60%   | 10   |\n"
            "| Wed | 82  | 66  | 10%   | 8    |\n\n"
            "## World News (1 stories)\n\n"
            "1. [Auto Story](https://example.com/auto)\n[Auto] Auto generated summary for this story. Some detail included here.\n\n"
            f"{PAD}\n"
        )
        path = _write_report(content)
        try:
            passed, issues = validate_report(path)
            fallback_issues = [i for i in issues if "Fallback marker" in i]
            self.assertEqual(len(fallback_issues), 0)
        finally:
            _cleanup(path)

    def test_headline_fallback_detected(self):
        # Need >10% bad and summaries must have 2+ sentences to reach the [Headline] check
        content = (
            "---\n"
            "title: Daily Brief\n"
            "date: 2026-07-29\n"
            "time_generated: 2026-07-29T12:00:00Z\n"
            "story_count_total: 10\n"
            "categories: 1\n"
            "tags:\n"
            "  - test\n"
            "---\n"
            "# Daily Brief\n\n"
            "## Weather Forecast 77316\n\n"
            "| Day | High | Low | Precip | Wind |\n"
            "|-----|------|-----|--------|------|\n"
            "| Mon | 85  | 68  | 0%    | 5    |\n"
            "| Tue | 80  | 65  | 60%   | 10   |\n"
            "| Wed | 82  | 66  | 10%   | 8    |\n\n"
            "## World News (10 stories)\n\n"
        )
        for i in range(1, 11):
            if i <= 2:
                content += f"{i}. [Bad Headline Story {i}](https://example.com/bad{i})\n[Headline] The headline was the only thing available at the time. No other data could be retrieved from the source.\n\n"
            else:
                content += f"{i}. [Good Story {i}](https://example.com/g{i})\nThis is a good summary of story {i}. It contains enough detail.\n\n"
        content += f"{PAD}\n"
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            headline_issues = [i for i in issues if "Fallback marker" in i]
            self.assertGreater(len(headline_issues), 0)
        finally:
            _cleanup(path)


# ---------------------------------------------------------------------------
# Topic mismatch
# ---------------------------------------------------------------------------

class TestTopicMismatch(TestCase):
    """Topic overlap check — significant headline words missing from summary."""

    def test_topic_mismatch_low_overlap(self):
        content = (
            "---\n"
            "title: Daily Brief\n"
            "date: 2026-07-29\n"
            "time_generated: 2026-07-29T12:00:00Z\n"
            "story_count_total: 10\n"
            "categories: 1\n"
            "tags:\n"
            "  - test\n"
            "---\n"
            "# Daily Brief\n\n"
            "## Weather Forecast 77316\n\n"
            "| Day | High | Low | Precip | Wind |\n"
            "|-----|------|-----|--------|------|\n"
            "| Mon | 85  | 68  | 0%    | 5    |\n"
            "| Tue | 80  | 65  | 60%   | 10   |\n"
            "| Wed | 82  | 66  | 10%   | 8    |\n\n"
            "## World News (10 stories)\n\n"
            "1. [Hurricane Damages Texas Coast](https://example.com/1)\nTotally unrelated summary about cooking recipes. Nothing about weather.\n\n"
        )
        for i in range(2, 11):
            content += f"{i}. [Good Story {i}](https://example.com/g{i})\nThis is a summary of story {i}. It has detail about the story.\n\n"
        content += f"{PAD}\n"
        path = _write_report(content)
        try:
            _, issues = validate_report(path)
            topic_issues = [i for i in issues if "Topic mismatch" in i]
            self.assertGreater(len(topic_issues), 0)
        finally:
            _cleanup(path)
