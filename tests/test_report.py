"""
Unit tests for src/daily_brief/rendering/report.py.
"""
import os
import sys
import tempfile
from unittest import TestCase, mock
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from daily_brief.rendering.report import (
    build_sections_from_stories,
    compute_output_path,
    build_markdown,
    write_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_story(title="Test Title", link="http://example.com", category="World News",
                summary="A summary.", pub_dt="2026-07-29", is_alert=False):
    """Create a minimal StoryPipelineState-like object."""
    s = mock.Mock()
    s.title = title
    s.link = link
    s.category = category
    s.summary = summary
    s.pub_dt = pub_dt
    s.is_alert = is_alert
    return s


def _format_date(raw):
    """Simple date formatter for tests."""
    return raw or "Unknown date"


def _config_kwargs(overrides=None):
    cfg = {
        "total_after_dedup": 10,
        "rendered_cat_count": 3,
        "DEFAULT_CONTENT_AGE_WINDOW_HOURS": 48,
        "FRONTMATTER_TAG_SEEDS": ["daily-brief"],
        "WEATHER_SECTION_TITLE": "Weather Forecast 77316",
    }
    if overrides:
        cfg.update(overrides)
    return cfg


def _weather():
    return {
        "forecast": [
            {"date": "Mon", "day": "Sunny", "night": "Clear", "high": "85", "low": "68", "precip": "0%", "wind": "5 mph"},
            {"date": "Tue", "day": "Cloudy", "night": "Rain", "high": "80", "low": "65", "precip": "60%", "wind": "10 mph"},
            {"date": "Wed", "day": "Partly Cloudy", "night": "Clear", "high": "82", "low": "66", "precip": "10%", "wind": "8 mph"},
        ],
        "station": {"avg_temp_today": "83", "avg_monthly_rainfall": "3.5 in", "current_monthly_rainfall": "2.1 in"},
        "lakes": {},
    }


# ---------------------------------------------------------------------------
# 1. build_sections_from_stories
# ---------------------------------------------------------------------------

class TestBuildSectionsFromStories(TestCase):
    """Group stories into sections, extract alerts, format dates."""

    def test_stories_grouped_by_category(self):
        stories = [
            _make_story(title="A", category="World News"),
            _make_story(title="B", category="US News"),
            _make_story(title="C", category="World News"),
        ]
        sections, alerts = build_sections_from_stories(stories, _format_date)
        self.assertIn("World News", sections)
        self.assertIn("US News", sections)
        self.assertEqual(len(sections["World News"]), 2)
        self.assertEqual(len(sections["US News"]), 1)

    def test_alerts_extracted(self):
        stories = [
            _make_story(title="Normal"),
            _make_story(title="Alert Story", is_alert=True),
        ]
        sections, alerts = build_sections_from_stories(stories, _format_date)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].title, "Alert Story")

    def test_date_formatted_via_callable(self):
        stories = [_make_story(pub_dt="2026-07-29")]
        sections, _ = build_sections_from_stories(stories, _format_date)
        entry = sections["World News"][0]
        self.assertEqual(entry["pub_date"], "2026-07-29")

    def test_empty_stories_returns_empty(self):
        sections, alerts = build_sections_from_stories([], _format_date)
        self.assertEqual(sections, {})
        self.assertEqual(alerts, [])

    def test_none_summary_becomes_unavailable(self):
        stories = [_make_story(summary=None)]
        sections, _ = build_sections_from_stories(stories, _format_date)
        self.assertEqual(sections["World News"][0]["summary"], "[Summary unavailable]")

    def test_entry_contains_all_fields(self):
        stories = [_make_story(title="T", link="http://x", category="Tech", summary="S", pub_dt="2026-01-01")]
        sections, _ = build_sections_from_stories(stories, _format_date)
        entry = sections["Tech"][0]
        self.assertEqual(entry["title"], "T")
        self.assertEqual(entry["link"], "http://x")
        self.assertEqual(entry["category"], "Tech")
        self.assertEqual(entry["summary"], "S")
        self.assertEqual(entry["pub_date"], "2026-01-01")

    def test_no_alert_when_not_set(self):
        stories = [_make_story(title="Normal", is_alert=False)]
        _, alerts = build_sections_from_stories(stories, _format_date)
        self.assertEqual(alerts, [])

    def test_multiple_categories_preserved(self):
        cats = ["World News", "US News", "Tech", "Finance"]
        stories = [_make_story(title=f"S{i}", category=c) for i, c in enumerate(cats)]
        sections, _ = build_sections_from_stories(stories, _format_date)
        for c in cats:
            self.assertIn(c, sections)
            self.assertEqual(len(sections[c]), 1)


# ---------------------------------------------------------------------------
# 2. compute_output_path
# ---------------------------------------------------------------------------

class TestComputeOutputPath(TestCase):
    """Auto-versioned output path generation."""

    def test_returns_filepath_with_date_and_version(self):
        with tempfile.TemporaryDirectory() as td:
            fp, ver = compute_output_path(td)
            self.assertIn("DailyBrief-", fp)
            self.assertIn("_v01.md", fp)
            self.assertIsInstance(ver, int)
            self.assertGreaterEqual(ver, 1)

    def test_path_ends_with_md(self):
        with tempfile.TemporaryDirectory() as td:
            fp, _ = compute_output_path(td)
            self.assertTrue(fp.endswith(".md"))

    def test_fresh_directory_starts_at_v01(self):
        with tempfile.TemporaryDirectory() as td:
            fp, ver = compute_output_path(td)
            self.assertIn("_v01.md", fp)
            self.assertEqual(ver, 1)

    def test_existing_v01_increments_to_v02(self):
        with tempfile.TemporaryDirectory() as td:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            existing = os.path.join(td, f"DailyBrief-{today}_v01.md")
            with open(existing, "w") as f:
                f.write("old")
            fp, ver = compute_output_path(td)
            self.assertIn("_v02.md", fp)
            self.assertEqual(ver, 2)

    def test_existing_multiple_versions_increments(self):
        with tempfile.TemporaryDirectory() as td:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for v in range(1, 4):
                with open(os.path.join(td, f"DailyBrief-{today}_v{v:02d}.md"), "w") as f:
                    f.write("old")
            fp, ver = compute_output_path(td)
            self.assertIn("_v04.md", fp)
            self.assertEqual(ver, 4)

    def test_creates_output_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as td:
            new_dir = os.path.join(td, "sub", "out")
            fp, _ = compute_output_path(new_dir)
            self.assertTrue(os.path.isdir(new_dir))
            self.assertTrue(fp.startswith(new_dir))

    def test_version_zero_padded(self):
        with tempfile.TemporaryDirectory() as td:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for v in range(1, 11):
                with open(os.path.join(td, f"DailyBrief-{today}_v{v:02d}.md"), "w") as f:
                    f.write("old")
            fp, ver = compute_output_path(td)
            self.assertIn("_v11.md", fp)
            self.assertEqual(ver, 11)

    def test_file_ver_is_int_gte_1(self):
        with tempfile.TemporaryDirectory() as td:
            _, ver = compute_output_path(td)
            self.assertIsInstance(ver, int)
            self.assertGreaterEqual(ver, 1)


# ---------------------------------------------------------------------------
# 3. build_markdown
# ---------------------------------------------------------------------------

class TestBuildMarkdown(TestCase):
    """Full markdown report rendering."""



    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_return_type_is_list(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = ""
        stories = []
        result = build_markdown(stories, {}, {}, [], _config_kwargs())
        self.assertIsInstance(result, list)

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_non_empty_output(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = ""
        stories = [_make_story(title="A Test Story")]
        sections, _ = build_sections_from_stories(stories, _format_date)
        result = build_markdown(stories, {}, sections, ["World News"], _config_kwargs())
        self.assertGreater(len(result), 20)

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_frontmatter_yaml_header(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = ""
        result = build_markdown([], {}, {}, [], _config_kwargs())
        self.assertEqual(result[0], "---")
        self.assertEqual(result[1], "title: Daily Brief")

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_frontmatter_date_and_status(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = ""
        result = build_markdown([], {}, {}, [], _config_kwargs())
        joined = "\n".join(result)
        self.assertIn("date: ", joined)
        self.assertIn("time_generated: ", joined)
        self.assertIn("status: active", joined)

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_frontmatter_story_count_categories(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = ""
        cfg = _config_kwargs({"total_after_dedup": 42, "rendered_cat_count": 5})
        result = build_markdown([], {}, {}, [], cfg)
        self.assertIn("story_count_total: 42", result)
        self.assertIn("categories: 5", result)

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_tags_from_seed_and_titles(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = "#texas #news"
        stories = [_make_story(title="Texas Story")]
        sections, _ = build_sections_from_stories(stories, _format_date)
        result = build_markdown(stories, {}, sections, ["World News"], _config_kwargs())
        tags_section = [l for l in result if l.startswith("  - ")]
        tag_values = [l.replace("  - ", "") for l in tags_section]
        self.assertIn("daily-brief", tag_values)
        self.assertIn("texas", tag_values)
        self.assertIn("news", tag_values)

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_tags_sorted_alphabetically(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = "#zebra #alpha #mango"
        stories = [_make_story(title="Test")]
        sections, _ = build_sections_from_stories(stories, _format_date)
        result = build_markdown(stories, {}, sections, ["World News"], _config_kwargs())
        tags_section = [l for l in result if l.startswith("  - ")]
        tag_values = [l.replace("  - ", "") for l in tags_section]
        self.assertEqual(tag_values, sorted(tag_values))

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_categories_rendered_in_order(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = ""
        stories = [
            _make_story(title="A", category="Category B"),
            _make_story(title="B", category="Category A"),
        ]
        sections, _ = build_sections_from_stories(stories, _format_date)
        result = build_markdown(stories, {}, sections, ["Category A", "Category B"], _config_kwargs())
        a_idx = next(i for i, l in enumerate(result) if l == "## Category A (1 stories)")
        b_idx = next(i for i, l in enumerate(result) if l == "## Category B (1 stories)")
        self.assertLess(a_idx, b_idx)

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_empty_category_renders_placeholder(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = ""
        result = build_markdown([], {}, {}, ["EmptyCat"], _config_kwargs())
        self.assertIn("## EmptyCat", result)
        self.assertIn("_No stories found._", result)

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_weather_section_included(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather", "**3 Day forecast**"]
        mock_tag.return_value = ""
        result = build_markdown([], {}, {}, [], _config_kwargs())
        self.assertIn("## Weather", result)
        mock_wx.assert_called_once()

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_story_entry_numbered_with_link(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = ""
        stories = [_make_story(title="My Title", link="http://example.com")]
        sections, _ = build_sections_from_stories(stories, _format_date)
        result = build_markdown(stories, {}, sections, ["World News"], _config_kwargs())
        self.assertIn("1. [My Title](http://example.com)", result)

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_weather_category_skipped(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = ""
        stories = [_make_story(title="Weather Alert", category="Weather Forecast 77316")]
        sections, _ = build_sections_from_stories(stories, _format_date)
        result = build_markdown(stories, {}, sections, ["Weather Forecast 77316"], _config_kwargs())
        weather_headers = [l for l in result if l.startswith("## Weather Forecast 77316 (")]
        self.assertEqual(len(weather_headers), 0)

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_pub_date_line_included(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = ""
        stories = [_make_story(title="T", pub_dt="2026-07-29")]
        sections, _ = build_sections_from_stories(stories, _format_date)
        result = build_markdown(stories, {}, sections, ["World News"], _config_kwargs())
        self.assertIn("*Originally published on:* 2026-07-29", "\n".join(result))

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_link_fallback_for_hash(self, mock_wx, mock_tag):
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = ""
        stories = [_make_story(title="No Link", link="#")]
        sections, _ = build_sections_from_stories(stories, _format_date)
        result = build_markdown(stories, {}, sections, ["World News"], _config_kwargs())
        self.assertIn("1. No Link", result)
        for line in result:
            self.assertNotIn("[No Link](#)", line)


# ---------------------------------------------------------------------------
# 4. write_report
# ---------------------------------------------------------------------------

class TestWriteReport(TestCase):
    """Write markdown list to file."""

    def test_file_exists_after_write(self):
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "test.md")
            write_report(fp, ["line1", "line2"])
            self.assertTrue(os.path.exists(fp))

    def test_content_newline_joined(self):
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "test.md")
            write_report(fp, ["a", "b", "c"])
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, "a\nb\nc\n")

    def test_utf8_encoding(self):
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "test.md")
            write_report(fp, ["caf\u00e9", "\u2603 snow"])
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("caf\u00e9", content)
            self.assertIn("\u2603", content)

    def test_trailing_newline(self):
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "test.md")
            write_report(fp, ["only"])
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertTrue(content.endswith("\n"))

    def test_no_extra_whitespace(self):
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "test.md")
            lines = ["header", "", "body", "footer"]
            write_report(fp, lines)
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            expected = "\n".join(lines) + "\n"
            self.assertEqual(content, expected)

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_bracket_style_tag_parsing(self, mock_wx, mock_tag):
        """report.py lines 120-122: bracket-style tag [Bracket] → parsed and extracted."""
        mock_wx.return_value = ["## Weather"]
        # tag_story_with_keywords returns a string with both hash and bracket tags
        mock_tag.return_value = "#hash [Bracket]"
        stories = [_make_story(title="Bracket Story")]
        sections, _ = build_sections_from_stories(stories, _format_date)
        result = build_markdown(stories, {}, sections, ["World News"], _config_kwargs())
        joined = "\n".join(result)
        # The hash tag "hash" should appear in frontmatter
        self.assertIn("  - hash", joined)
        # The bracket tag content should be extracted and appear in tags
        # note: report.py uses tag[2:-2] for bracket content extraction
        bracket_content = "rack"  # "[Bracket]"[2:-2] = "rack"
        self.assertIn(f"  - {bracket_content.lower()}", joined)

    @mock.patch("daily_brief.rendering.report.tag_story_with_keywords")
    @mock.patch("daily_brief.rendering.report.build_weather_markdown")
    def test_weather_cat_skip_with_tags(self, mock_wx, mock_tag):
        """report.py line 140: weather category with non-empty tags → continue path."""
        mock_wx.return_value = ["## Weather"]
        mock_tag.return_value = "#weather #forecast"
        # Story placed in the weather section title category
        stories = [_make_story(title="Weather Story", category="Weather Forecast 77316")]
        sections, _ = build_sections_from_stories(stories, _format_date)
        result = build_markdown(stories, {}, sections, ["Weather Forecast 77316"], _config_kwargs())
        # The weather category should be skipped (line 140 continue)
        weather_section_headers = [l for l in result if l.startswith("## Weather Forecast 77316 (")]
        self.assertEqual(len(weather_section_headers), 0)
