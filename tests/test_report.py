"""
Unit tests for daily_brief/rendering/report.py.
"""
import os
import re
import tempfile
from unittest import TestCase, mock
from datetime import datetime, timezone

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
                summary="A summary.", pub_dt="2026-07-29"):
    """Create a minimal StoryPipelineState-like object."""
    s = mock.Mock()
    s.title = title
    s.link = link
    s.category = category
    s.summary = summary
    s.pub_dt = pub_dt
    return s


def _format_date(raw):
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
    """Group stories into sections, format dates."""

    def test_grouping_and_entry_fields(self):
        """Story-to-section mapping: grouped by category, all fields present."""
        stories = [
            _make_story(title="A", category="World News"),
            _make_story(title="B", category="US News"),
            _make_story(title="C", link="http://c", category="World News", summary="C summary", pub_dt="2026-01-02"),
        ]
        sections = build_sections_from_stories(stories, _format_date)
        assert "World News" in sections
        assert "US News" in sections
        assert len(sections["World News"]) == 2
        assert len(sections["US News"]) == 1
        # Entry fields preserved
        entry = sections["World News"][1]
        assert entry["title"] == "C"
        assert entry["link"] == "http://c"
        assert entry["category"] == "World News"
        assert entry["summary"] == "C summary"
        assert entry["pub_date"] == "2026-01-02"
        # Date formatted via callable
        assert sections["World News"][0]["pub_date"] == "2026-07-29"

    def test_empty_stories_returns_empty(self):
        assert build_sections_from_stories([], _format_date) == {}

    def test_none_summary_fallback(self):
        sections = build_sections_from_stories([_make_story(summary=None)], _format_date)
        assert sections["World News"][0]["summary"] == "[Summary unavailable]"


# ---------------------------------------------------------------------------
# 2. compute_output_path
# ---------------------------------------------------------------------------

class TestComputeOutputPath(TestCase):
    """Auto-versioned output path generation."""

    def test_fresh_dir_auto_v01(self):
        with tempfile.TemporaryDirectory() as td:
            fp, ver = compute_output_path(td)
            assert ver == 1
            assert isinstance(fp, str)
            assert fp.endswith("_v01.md")

    def test_existing_versions_increment(self):
        with tempfile.TemporaryDirectory() as td:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for v in range(1, 4):
                with open(os.path.join(td, f"DailyBrief-{today}_v{v:02d}.md"), "w") as f:
                    f.write("old")
            fp, ver = compute_output_path(td)
            assert ver == 4
            assert "_v04.md" in fp

    def test_explicit_file_ver_auto(self):
        with tempfile.TemporaryDirectory() as td:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for v in range(1, 9):
                with open(os.path.join(td, f"DailyBrief-{today}_v{v:02d}.md"), "w") as f:
                    f.write("old")
            fp, ver = compute_output_path(td, file_ver=15)
            assert ver == 15
            assert fp == os.path.join(td, f"DailyBrief-{today}_v15.md")

    def test_explicit_file_ver_empty(self):
        with tempfile.TemporaryDirectory() as td:
            fp, ver = compute_output_path(td, file_ver=7)
            assert ver == 7
            assert "_v07.md" in fp

    def test_creates_output_dir(self):
        with tempfile.TemporaryDirectory() as td:
            new_dir = os.path.join(td, "sub", "out")
            fp, _ = compute_output_path(new_dir)
            assert os.path.isdir(new_dir)
            assert fp.startswith(new_dir)

    def test_version_two_digit_padding(self):
        with tempfile.TemporaryDirectory() as td:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for v in range(1, 11):
                with open(os.path.join(td, f"DailyBrief-{today}_v{v:02d}.md"), "w") as f:
                    f.write("old")
            fp, ver = compute_output_path(td)
            assert ver == 11
            assert "_v11.md" in fp


# ---------------------------------------------------------------------------
# 3. build_markdown
# ---------------------------------------------------------------------------

class TestBuildMarkdown(TestCase):
    """Full markdown report rendering."""

    def _build(self, stories, sections=None, cats=None, cfg=None, tag_return="", wx_lines=None):
        if sections is None:
            sections = build_sections_from_stories(stories, _format_date)
        if cats is None:
            cats = list(sections.keys())
        if cfg is None:
            cfg = _config_kwargs()
        if wx_lines is None:
            wx_lines = ["## Weather"]
        with (
            mock.patch("daily_brief.rendering.report.build_weather_markdown", return_value=wx_lines),
            mock.patch("daily_brief.rendering.report.tag_story_with_keywords", return_value=tag_return),
        ):
            return build_markdown(stories, {}, sections, cats, cfg)

    def test_full_markdown_golden_shape(self):
        """Complete output: frontmatter -> header -> weather -> categories -> story entries."""
        stories = [
            _make_story(title="My Title", link="http://example.com", category="World News",
                        summary="A summary.", pub_dt="2026-07-29"),
            _make_story(title="Second", link="http://two.com", category="Tech",
                        summary="Another summary.", pub_dt="2026-07-30"),
        ]
        sections = build_sections_from_stories(stories, _format_date)
        result = self._build(stories, sections, cats=["Tech", "World News"])
        joined = "\n".join(result)
        # Must be a list
        assert isinstance(result, list)
        assert len(result) > 20
        # Frontmatter
        assert result[0] == "---"
        assert result[1] == "title: Daily Brief"
        assert any("date: " in l for l in result)
        assert any("time_generated: " in l for l in result)
        assert any("status: active" in l for l in result)
        assert "story_count_total: 10" in result
        assert "categories: 3" in result
        assert "tags:" in result
        assert "---" in result  # closing YAML delimiter
        # H1 header
        assert any(l.startswith("# Daily Brief --") for l in result)
        # Weather from build_weather_markdown
        assert "## Weather" in result
        # Category ordering: Tech before World News
        tech_idx = next(i for i, l in enumerate(result) if l.startswith("## Tech"))
        wn_idx = next(i for i, l in enumerate(result) if l == "## World News (1 stories)")
        assert tech_idx < wn_idx
        # Numbered story entry with link
        assert "1. [My Title](http://example.com)" in result
        assert "1. [Second](http://two.com)" in result
        # Pub date line
        assert "*Originally published on:* 2026-07-29" in joined
        # Category section header with count
        assert "## World News (1 stories)" in result
        assert "## Tech (1 stories)" in result

    def test_empty_category_header_render(self):
        """Empty categories render a header with placeholder text."""
        result = self._build([], sections={}, cats=["EmptyCat"], cfg=_config_kwargs({"rendered_cat_count": 1}))
        assert "## EmptyCat" in result
        assert "_No stories found._" in result
        # Verify empty categories count in frontmatter
        result2 = self._build(
            [_make_story(title="A", category="Populated")],
            cats=["Populated", "EmptyCat"],
            cfg=_config_kwargs({"rendered_cat_count": 2}),
        )
        assert "categories: 2" in result2
        assert "## Populated (1 stories)" in result2
        assert "## EmptyCat" in result2
        assert "_No stories found._" in result2

    def test_tag_extraction_hash_and_bracket(self):
        """Hash tags and bracket-style tags both extracted and sorted."""
        with (
            mock.patch("daily_brief.rendering.report.build_weather_markdown", return_value=["## Weather"]),
            mock.patch("daily_brief.rendering.report.tag_story_with_keywords", return_value="#texas #news [Bracket]"),
        ):
            stories = [_make_story(title="Texas Story")]
            sections = build_sections_from_stories(stories, _format_date)
            result = build_markdown(stories, {}, sections, ["World News"], _config_kwargs())
        tags_section = [l for l in result if l.startswith("  - ")]
        tag_values = [l.replace("  - ", "") for l in tags_section]
        assert "daily-brief" in tag_values
        assert "texas" in tag_values
        assert "news" in tag_values
        assert tag_values == sorted(tag_values), "Tags must be alphabetically sorted"

    def test_safe_no_link_render(self):
        """link='#' → plain text heading without markdown link."""
        stories = [_make_story(title="No Link", link="#")]
        sections = build_sections_from_stories(stories, _format_date)
        result = self._build(stories, sections, cats=["World News"])
        assert "1. No Link" in result
        for line in result:
            assert "[No Link](#)" not in line

    def test_weather_category_skipped(self):
        """Stories in the weather section category are not rendered as a section."""
        stories = [_make_story(title="Weather Alert", category="Weather Forecast 77316")]
        sections = build_sections_from_stories(stories, _format_date)
        result = self._build(stories, sections, cats=["Weather Forecast 77316"])
        weather_section_headers = [l for l in result if l.startswith("## Weather Forecast 77316 (")]
        assert len(weather_section_headers) == 0


# ---------------------------------------------------------------------------
# 4. write_report
# ---------------------------------------------------------------------------

class TestWriteReport(TestCase):
    """Write markdown list to file."""

    def test_utf8_write_newlines(self):
        """UTF-8 encoding, newline-joined content, trailing newline."""
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "test.md")
            write_report(fp, ["caf\u00e9", "\u2603 snow", "line3"])
            assert os.path.exists(fp)
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            assert "caf\u00e9" in content
            assert "\u2603" in content
            assert content == "caf\u00e9\n\u2603 snow\nline3\n"
        # No extra whitespace
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "test2.md")
            write_report(fp, ["header", "", "body", "footer"])
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            assert content == "header\n\nbody\nfooter\n"

    def test_write_report_uses_temp_file_and_rename(self):
        """Atomic write: temp file opened before final path via os.replace."""
        import builtins
        opened_paths = []
        original_open = builtins.open

        def tracking_open(path, *args, **kwargs):
            opened_paths.append(path)
            return original_open(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "test.md")
            with mock.patch("builtins.open", side_effect=tracking_open):
                write_report(fp, ["line1", "line2"])
        tmp_path = fp + ".tmp"
        assert tmp_path in opened_paths
        tmp_idx = opened_paths.index(tmp_path)
        assert tmp_idx < len(opened_paths) - 1

    def test_write_report_failure_preserves_previous(self):
        """On write failure, the original file remains intact."""
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "test.md")
            old_content = "original content\n"
            with open(fp, "w", encoding="utf-8") as f:
                f.write(old_content)

            call_count = [0]
            original_open = __builtins__["open"] if isinstance(__builtins__, dict) else __builtins__.open

            def failing_open(path, *args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise IOError("simulated write failure")
                return original_open(path, *args, **kwargs)

            try:
                with mock.patch("builtins.open", side_effect=failing_open):
                    write_report(fp, ["new", "content"])
            except IOError:
                pass

            assert os.path.exists(fp)
            with open(fp, "r", encoding="utf-8") as f:
                assert f.read() == old_content

    def test_write_report_cleanup_temp_on_failure(self):
        """On write failure, no .tmp artifact remains."""
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "test.md")
            tmp_path = fp + ".tmp"

            call_count = [0]
            original_open = __builtins__["open"] if isinstance(__builtins__, dict) else __builtins__.open

            def failing_open(path, *args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise IOError("simulated write failure")
                return original_open(path, *args, **kwargs)

            try:
                with mock.patch("builtins.open", side_effect=failing_open):
                    write_report(fp, ["new", "content"])
            except IOError:
                pass

            assert not os.path.exists(tmp_path)

    def test_write_report_same_dir_temp(self):
        """The temp file path is in the same directory as the target."""
        import builtins
        opened_paths = []
        original_open = builtins.open

        def tracking_open(path, *args, **kwargs):
            opened_paths.append(path)
            return original_open(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "sub", "test.md")
            os.makedirs(os.path.join(td, "sub"), exist_ok=True)
            with mock.patch("builtins.open", side_effect=tracking_open):
                write_report(fp, ["line1"])
        tmp_path = os.path.join(td, "sub", "test.md.tmp")
        assert tmp_path in opened_paths
        assert os.path.dirname(tmp_path) == os.path.dirname(fp)
