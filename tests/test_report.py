"""Direct tests for report.py contracts lost in earlier ratio fix."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from daily_brief.rendering.report import (
    build_markdown,
    build_sections_from_stories,
    compute_output_path,
    write_report,
)


def test_output_path_auto_versions_and_honors_explicit(tmp_path):
    out = tmp_path / "reports"
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    first, ver = compute_output_path(out)
    assert out.is_dir() and ver == 1 and f"_v01.md" in first
    existing = out / f"DailyBrief-{day}_v09.md"
    existing.write_text("old")
    path, ver = compute_output_path(out)
    assert ver == 10 and f"_v10.md" in path
    path, ver = compute_output_path(out, file_ver=15)
    assert ver == 15 and f"_v15.md" in path


def test_sections_group_stories_format_pub_fallback_summary():
    stories = [
        SimpleNamespace(title="A", link="a", category="One", summary="", pub_dt="x"),
        SimpleNamespace(title="B", link="b", category="Two", summary="B summary", pub_dt="y"),
        SimpleNamespace(title="C", link="c", category="One", summary="C summary", pub_dt="z"),
    ]
    sections = build_sections_from_stories(stories, lambda v: f"date:{v}")
    assert list(sections) == ["One", "Two"]
    assert len(sections["One"]) == 2
    assert sections["One"][0]["summary"] == "[Summary unavailable]"
    assert sections["One"][0]["pub_date"] == "date:x"


def test_markdown_empty_category_plain_no_link_and_sorted_tags():
    sections = {"News": [{"title": "No link", "link": "#", "summary": "Summary", "pub_date": ""}]}
    config = dict(
        total_after_dedup=1,
        rendered_cat_count=2,
        DEFAULT_CONTENT_AGE_WINDOW_HOURS=48,
        FRONTMATTER_TAG_SEEDS=["seed"],
        WEATHER_SECTION_TITLE="Weather",
    )
    with (
        patch("daily_brief.rendering.report.build_weather_markdown", return_value=[]),
        patch("daily_brief.rendering.report.tag_story_with_keywords", return_value="#Alpha [Beta]"),
    ):
        md = build_markdown([], {}, sections, ["Empty", "News"], config)
    text = "\n".join(md)
    assert "## Empty\n_No stories found._" in text
    assert "[No link](#)" not in text
    tags = [line[4:] for line in md if line.startswith("  - ")]
    assert tags == ["alpha", "beta", "seed"]


def test_write_report_utf8_trailing_newline_and_cleans_failed_tmp(tmp_path):
    report = tmp_path / "report.md"
    write_report(str(report), ["cafe", "\u2603 snow"])
    assert report.read_bytes() == "cafe\n\u2603 snow\n".encode("utf-8")
    report.write_text("old\n", encoding="utf-8")
    with patch("daily_brief.rendering.report.os.fsync", side_effect=OSError("disk full")):
        try:
            write_report(str(report), ["new"])
        except OSError:
            pass
    assert report.read_text(encoding="utf-8") == "old\n"
    assert not (tmp_path / "report.md.tmp").exists()
