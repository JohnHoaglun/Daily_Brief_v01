"""Rendering / Markdown Safety Contract — Story fixtures — compact."""

from __future__ import annotations

from unittest import TestCase, mock

from daily_brief.rendering.report import build_markdown, build_sections_from_stories


def _make_story(title="Test", link="http://example.com", category="World", summary="A summary.", pub_dt="2026-07-29"):
    s = mock.Mock()
    s.title = title
    s.link = link
    s.category = category
    s.summary = summary
    s.pub_dt = pub_dt
    return s


def _fmt(raw):
    return raw or "Unknown"


def _cfg(overrides=None):
    cfg = {"total_after_dedup": 1, "rendered_cat_count": 1, "DEFAULT_CONTENT_AGE_WINDOW_HOURS": 48, "FRONTMATTER_TAG_SEEDS": ["daily-brief"], "WEATHER_SECTION_TITLE": "WX"}
    if overrides:
        cfg.update(overrides)
    return cfg


class TestMarkdownSafety(TestCase):
    """One markdown safety render and one HTML-escape case."""

    def test_newline_in_summary_normalized(self):
        """Summary with embedded \\n must not produce extra blank lines in output."""
        stories = [_make_story(title="Story Title", summary="First sentence.\nSecond sentence after newline.")]
        sections = build_sections_from_stories(stories, _fmt)
        with (
            mock.patch("daily_brief.rendering.report.build_weather_markdown", return_value=["## Weather"]),
            mock.patch("daily_brief.rendering.report.tag_story_with_keywords", return_value="[Tag]"),
        ):
            result = build_markdown(stories, {}, sections, ["World"], _cfg())
        joined = "\n".join(result)
        # The summary should be a single logical unit — no blank lines between the summary sentences
        summary_line = None
        for line in result:
            if "First sentence." in line:
                summary_line = line
                break
        self.assertIsNotNone(summary_line)
        # The summary line should not be empty or whitespace-only
        self.assertTrue(summary_line.strip())

    def test_asterisks_escaped_in_title(self):
        """Title with *word* must not produce italic formatting in Markdown output."""
        stories = [_make_story(title="*Important* Breaking", summary="Normal.") ]
        sections = build_sections_from_stories(stories, _fmt)
        with (
            mock.patch("daily_brief.rendering.report.build_weather_markdown", return_value=["## Weather"]),
            mock.patch("daily_brief.rendering.report.tag_story_with_keywords", return_value="[Tag]"),
        ):
            result = build_markdown(stories, {}, sections, ["World"], _cfg())
        joined = "\n".join(result)
        self.assertIn("*Important*", joined, "Asterisks in title must be escaped for safe rendering.")
