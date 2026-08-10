"""Regression tests characterizing current external behavior of batch_summarize_all().
Must pass with current code before and after C.4 refactoring."""

import asyncio
from unittest import TestCase, mock
from unittest.mock import AsyncMock, MagicMock

from daily_brief.llm.summarizer import (
    StoryPipelineState,
    batch_summarize_all,
)


def _make_story(
    title,
    category,
    snippet="Snip.",
    context="Article content long enough for context processing by the LLM summary system.",
):
    s = StoryPipelineState(
        title=title, link="http://x", snippet=snippet, pub_dt="2024-01-01", category=category
    )
    s.context = context
    s.summary = None
    return s


def _retry_patches():
    return (
        mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_ATTEMPTS", 1),
        mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_BACKOFF", []),
        mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None),
    )


def _is_batch(msgs):
    if not msgs:
        return False
    system = msgs[0].get("content", "") if isinstance(msgs[0], dict) else ""
    return "STORY_0" in system


class TestBatchValidSummariesRetained(TestCase):
    def test_all_stories_valid(self):
        stories = [
            _make_story("Alpha Finance Market Rally Today", "Finance"),
            _make_story("Beta Finance Bond Yield Increase", "Finance"),
            _make_story("Gamma Finance IPO Listing Success", "Finance"),
            _make_story("Delta Tech AI Chip Design", "Tech"),
            _make_story("Epsilon Tech Software Release", "Tech"),
        ]

        async def side_effect(**kwargs):
            msgs = kwargs.get("messages", [])
            if _is_batch(msgs):
                user = msgs[1].get("content", "")
                blocks = user.split("\n---\n\n")
                hls = []
                for block in blocks:
                    for line in block.strip().split("\n"):
                        if line and not line.startswith(("1. ", "2. ", "3. ")):
                            hls.append(line.strip())
                            break
                parts = []
                for i, hl in enumerate(hls):
                    parts.append(
                        f"STORY_{i} | {hl}={hl} summary with detailed analysis and concrete facts. "
                        f"Important findings reported across the sector today."
                    )
                content = "\n".join(parts)
                r = MagicMock()
                r.choices = [MagicMock(message=MagicMock(content=content))]
                return r
            r = MagicMock()
            r.choices = [MagicMock(message=MagicMock(content="Fallback."))]
            return r

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                await batch_summarize_all(client, stories, batch_size=3)

        asyncio.get_event_loop().run_until_complete(run())
        for s in stories:
            self.assertNotIn("[Auto]", s.summary)
            self.assertTrue(len(s.summary) > 0)


class TestBatchFallbackText(TestCase):
    def test_batch_fail_recovery_fail_auto(self):
        stories = [_make_story("Theta News Breaking Story", "News")]

        async def side_effect(**kwargs):
            raise Exception("Connection refused")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                with mock.patch(
                    "daily_brief.llm.summarizer._summarize",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    await batch_summarize_all(client, stories, batch_size=1)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(stories[0].summary.startswith("[Auto]"))

    def test_batch_fail_recovery_succeed(self):
        stories = [_make_story("Iota Tech Recovery Story", "Tech")]

        async def side_effect(**kwargs):
            raise Exception("Batch error")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                with mock.patch(
                    "daily_brief.llm.summarizer._summarize",
                    new_callable=AsyncMock,
                    return_value="Recovered summary with real facts about the tech story. Analysts confirmed the findings.",
                ):
                    await batch_summarize_all(client, stories, batch_size=1)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertNotIn("[Auto]", stories[0].summary)


class TestBatchCategoryGrouping(TestCase):
    def test_same_category_one_batch(self):
        stories = [
            _make_story("Kappa Finance Story One", "Finance"),
            _make_story("Lambda Finance Story Two", "Finance"),
            _make_story("Mu Finance Story Three", "Finance"),
        ]
        call_count = [0]

        async def side_effect(**kwargs):
            if _is_batch(kwargs.get("messages", [])):
                call_count[0] += 1
            r = MagicMock()
            r.choices = [MagicMock(message=MagicMock(content=""))]
            return r

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                with mock.patch(
                    "daily_brief.llm.summarizer._summarize",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    await batch_summarize_all(client, stories, batch_size=5)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(call_count[0], 2, "3 same-category stories: 1 initial + 1 retry batch")

    def test_diff_categories_separate_batches(self):
        stories = [
            _make_story("Nu Tech Story", "Tech"),
            _make_story("Xi News Story", "News"),
        ]
        batch_count = [0]

        async def side_effect(**kwargs):
            if _is_batch(kwargs.get("messages", [])):
                batch_count[0] += 1
            r = MagicMock()
            r.choices = [MagicMock(message=MagicMock(content=""))]
            return r

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                with mock.patch(
                    "daily_brief.llm.summarizer._summarize",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    await batch_summarize_all(client, stories, batch_size=5)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(batch_count[0], 4, "2 different categories: 2 initial + 2 retry batches")


class TestBatchOrderingPreserved(TestCase):
    def test_category_grouping_preserved(self):
        stories = [
            _make_story("Omicron Cat A Story", "CatA"),
            _make_story("Pi Cat B Story", "CatB"),
            _make_story("Rho Cat A Story", "CatA"),
            _make_story("Sigma Cat B Story", "CatB"),
        ]
        batch_order = []

        async def side_effect(**kwargs):
            msgs = kwargs.get("messages", [])
            if _is_batch(msgs):
                user = msgs[1].get("content", "")
                if "CatA" in user:
                    batch_order.append("CatA")
                elif "CatB" in user:
                    batch_order.append("CatB")
            r = MagicMock()
            r.choices = [MagicMock(message=MagicMock(content=""))]
            return r

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                with mock.patch(
                    "daily_brief.llm.summarizer._summarize",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    await batch_summarize_all(client, stories, batch_size=5)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(len(batch_order), 4, "Should have 4 batch calls (2 initial + 2 retry)")


class TestBatchConcurrencyIsolation(TestCase):
    def test_concurrency_1_serial(self):
        stories = [
            _make_story("Psi Tech", "Tech"),
            _make_story("Omega News", "News"),
        ]
        active = [0]
        max_active = [0]

        async def side_effect(**kwargs):
            active[0] += 1
            max_active[0] = max(max_active[0], active[0])
            await asyncio.sleep(0.03)
            active[0] -= 1
            r = MagicMock()
            r.choices = [MagicMock(message=MagicMock(content=""))]
            return r

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                with mock.patch(
                    "daily_brief.llm.summarizer._summarize",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    await batch_summarize_all(client, stories, batch_size=1, max_concurrency=1)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(max_active[0], 1, "max_concurrency=1 should be serial")


class TestBatchEmptyInput(TestCase):
    def test_empty_stories(self):
        client = MagicMock()
        client.chat_completions_create = AsyncMock()

        async def run():
            return await batch_summarize_all(client, [])

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(result.total_stories, 0)
        stories = [_make_story("Alpha Boil Testing", "Cat")]

        async def side_effect(**kwargs):
            r = MagicMock()
            r.choices = [
                MagicMock(
                    message=MagicMock(
                        content=(
                            "STORY_0 | Alpha Boil Testing=This article discusses the implications of the new policy."
                        )
                    )
                )
            ]
            return r

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                with mock.patch(
                    "daily_brief.llm.summarizer._summarize",
                    new_callable=AsyncMock,
                    return_value="Valid recovery for the Alpha boil testing. Two sentences here for the story.",
                ):
                    await batch_summarize_all(client, stories, batch_size=1)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertIn("Valid recovery", stories[0].summary)
