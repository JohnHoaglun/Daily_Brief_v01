"""Regression tests characterizing current external behavior of batch_summarize_all().
Must pass with current code before and after C.4 refactoring."""
import asyncio
import time
from unittest import TestCase, mock
from unittest.mock import AsyncMock, MagicMock

from daily_brief.llm.summarizer import (
    StoryPipelineState,
    batch_summarize_all,
)


def _make_story(title, category, snippet="Snip.", context="Article content long enough for context processing by the LLM summary system."):
    s = StoryPipelineState(title=title, link="http://x", snippet=snippet, pub_dt="2024-01-01", category=category)
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
        ]

        async def side_effect(**kwargs):
            msgs = kwargs.get("messages", [])
            if _is_batch(msgs):
                content = (
                    "STORY_0 | Alpha Finance Market Rally=Market rally gained strong momentum today with tech leading gains. "
                    "The S&P 500 closed at record highs during afternoon trading.\n"
                    "STORY_1 | Beta Finance Bond Yield=Bond yields increased sharply following treasury auction results this morning. "
                    "The 10-year note climbed to a six-week high in active trading.\n"
                    "STORY_2 | Gamma Finance IPO Listing=The IPO listing was successful with shares gaining 15 percent on first day. "
                    "Investors poured billions into the new offering during opening bell."
                )
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
                with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                    await batch_summarize_all(client, stories, batch_size=3)

        asyncio.get_event_loop().run_until_complete(run())
        for s in stories:
            self.assertNotIn("[Auto]", s.summary)
            self.assertTrue(len(s.summary) > 0)

    def test_two_stories_both_valid(self):
        stories = [
            _make_story("Delta Tech AI Chip Design", "Tech"),
            _make_story("Epsilon Tech Software Release", "Tech"),
        ]

        async def side_effect(**kwargs):
            r = MagicMock()
            r.choices = [MagicMock(message=MagicMock(content=(
                "STORY_0 | Delta Tech AI Chip=AI chip design breakthrough announced today with 5-nanometer process. "
                "The new architecture promises 40 percent performance gains over previous generation.\n"
                "STORY_1 | Epsilon Tech Software=Software release includes major security patches and performance improvements. "
                "Users reported significant speed increases after installing the update."
            )))]
            return r

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                await batch_summarize_all(client, stories, batch_size=2)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertNotIn("[Auto]", stories[0].summary)
        self.assertNotIn("[Auto]", stories[1].summary)


class TestBatchFallbackText(TestCase):
    def test_batch_fail_recovery_fail_auto(self):
        stories = [_make_story("Theta News Breaking Story", "News")]

        async def side_effect(**kwargs):
            raise Exception("Connection refused")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
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
                with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock,
                        return_value="Recovered summary with real facts about the tech story. Analysts confirmed the findings."):
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
                with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
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
                with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
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
                with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                    await batch_summarize_all(client, stories, batch_size=5)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(len(batch_order), 4, "Should have 4 batch calls (2 initial + 2 retry)")


class TestBatchConcurrencyIsolation(TestCase):
    def test_concurrency_2_parallel(self):
        stories = [
            _make_story("Tau Tech One", "Tech"),
            _make_story("Upsilon Tech Two", "Tech"),
            _make_story("Phi News One", "News"),
            _make_story("Chi News Two", "News"),
        ]

        async def side_effect(**kwargs):
            await asyncio.sleep(0.03)
            r = MagicMock()
            r.choices = [MagicMock(message=MagicMock(content=""))]
            return r

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                    await batch_summarize_all(client, stories, batch_size=2, max_concurrency=2)

        asyncio.get_event_loop().run_until_complete(run())

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
                with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
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


class TestBatchBoilerplateDetection(TestCase):
    def test_boilerplate_marked_empty(self):
        stories = [_make_story("Alpha Boil Testing", "Cat")]

        async def side_effect(**kwargs):
            r = MagicMock()
            r.choices = [MagicMock(message=MagicMock(content=(
                "STORY_0 | Alpha Boil Testing=This article discusses the implications of the new policy."
            )))]
            return r

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock,
                        return_value="Valid recovery for the Alpha boil testing. Two sentences here for the story."):
                    await batch_summarize_all(client, stories, batch_size=1)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertIn("Valid recovery", stories[0].summary)

    def test_refusal_in_recovery_falls_to_auto(self):
        stories = [_make_story("Beta Refusal Test", "Cat")]

        async def side_effect(**kwargs):
            raise Exception("fail")

        client = MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def run():
            with _retry_patches()[0], _retry_patches()[1], _retry_patches()[2]:
                with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock,
                        return_value="I cannot summarize this without the source text."):
                    await batch_summarize_all(client, stories, batch_size=1)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(stories[0].summary.startswith("[Auto]"))


class TestBatchAsyncRetry(TestCase):
    def test_uses_asyncio_sleep(self):
        import inspect
        src = inspect.getsource(batch_summarize_all)
        self.assertNotIn("time.sleep", src, "batch_summarize_all should not use time.sleep")
