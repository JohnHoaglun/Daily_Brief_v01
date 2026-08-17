"""Shared helpers for concurrency tests."""

import asyncio
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp as _aiohttp_mod

import daily_brief.pipeline as _pipeline_mod


def _restore_aiohttp_client_session():
    """Restore daily_brief.pipeline.aiohttp.ClientSession to the real class."""
    _pipeline_mod.aiohttp.ClientSession = _aiohttp_mod.ClientSession


def _make_async_cm():
    """Mock async context manager (stand-in for aiohttp.ClientSession)."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=MagicMock())
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _story(
    title="StoryTitle",
    summary="Good summary detail here. Enough detail.",
    link="https://example.com/1",
    category="cat",
):
    s = MagicMock()
    s.title = title
    s.summary = summary
    s.link = link
    s.published = None
    s.category = category
    s.full_article = None
    return s


def _default_dedup_data(stories=None):
    if stories is None:
        stories = [("StoryTitle", "https://example.com/1", "snip", None, "cat")]
    return (stories, {"total_after": len(stories)})


def _weather():
    return {
        "forecast": [{"period": 1}],
        "station": {
            "avg_temp_today": "75",
            "avg_monthly_rainfall": "3",
            "current_hourly_rainfall": "2",
        },
        "lakes": {},
    }


def _pipeline_patch_group(
    tmpdir,
    dedup_data=None,
    weather=None,
    llm_side_effect=None,
    extract_mock=None,
    section_return=None,
    categories=None,
):
    """Build the standard set of patches for one pipeline invocation."""
    if dedup_data is None:
        dedup_data = _default_dedup_data()
    if weather is None:
        weather = _weather()
    if section_return is None:
        section_return = {"cat": [_story()]}
    if categories is None:
        categories = ["cat"]
    patches = [
        patch("daily_brief.pipeline.LOG_DIR", tmpdir),
        patch("daily_brief.pipeline.NEWS_DIR", tmpdir),
        patch("daily_brief.pipeline.aiohttp.ClientSession", return_value=_make_async_cm()),
        patch("daily_brief.pipeline.write_report"),
        patch("daily_brief.pipeline.validate_config", return_value=(True, [])),
        patch("daily_brief.pipeline.fetch_weather", new_callable=AsyncMock, return_value=weather),
        patch(
            "daily_brief.pipeline.fetch_and_dedup", new_callable=AsyncMock, return_value=dedup_data
        ),
        patch(
            "daily_brief.pipeline.StoryPipelineState",
            side_effect=lambda *a, **kw: _story(
                category=dedup_data[0][0][4] if dedup_data[0] else "cat"
            ),
        ),
        patch("daily_brief.pipeline.stage_extract_article", new_callable=AsyncMock)
        if extract_mock is None
        else patch("daily_brief.pipeline.stage_extract_article", side_effect=extract_mock),
        patch("daily_brief.pipeline.llm_batch_summarize_all", new_callable=AsyncMock),
        patch("daily_brief.pipeline.build_sections_from_stories", return_value=section_return),
        patch("daily_brief.pipeline.ordered_categories_for_render", return_value=categories),
        patch("daily_brief.pipeline.cleanup_old_files"),
        patch("daily_brief.pipeline.build_markdown", return_value=["#md"]),
        patch("daily_brief.pipeline.validate_report", return_value=(True, [])),
        patch("daily_brief.pipeline.PREFLIGHT_CHECKS_ENABLED", False),
    ]
    if llm_side_effect is not None:
        patches.append(
            patch("daily_brief.pipeline.create_llm_client", side_effect=llm_side_effect)
        )
    else:
        patches.append(patch("daily_brief.pipeline.create_llm_client", return_value=MagicMock()))
    return patches


class _NestedCM:
    """Enter multiple lists of patches as nested context managers."""

    def __init__(self, patch_lists):
        self.patch_lists = patch_lists
        self.entries = []

    def __enter__(self):
        for pl in self.patch_lists:
            self.entries.append([p.__enter__() for p in pl])
        return self.entries

    def __exit__(self, *exc):
        for pl in reversed(self.patch_lists):
            for p in reversed(pl):
                p.__exit__(*exc)
