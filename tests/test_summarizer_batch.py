"""
Batch scheduling and recovery unit tests for daily_brief/llm/summarizer.py.
Split from test_summarizer.py.
"""

import asyncio
from unittest import TestCase, mock
from unittest.mock import AsyncMock

from daily_brief.llm.summarizer import (
    StoryPipelineState,
    batch_summarize_all,
)

# ---------------------------------------------------------------------------
# batch_summarize_all
# ---------------------------------------------------------------------------


class TestBatchSummarizeAll(TestCase):
    """batch_summarize_all integration with mocked async client (Perf-8)."""

    def _make_story(self, title, category, context=None, snippet=None):

        s = StoryPipelineState(title, "http://x", snippet or "", "2024-01-01", category)
        s.context = context
        s.summary = None
        return s

    def test_batch_summarize_all_empty(self):
        client = mock.MagicMock()

        async def _run():
            return await batch_summarize_all(client, [])

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result.total_stories, 0)

    def test_batch_summarize_all_with_retries(self):
        stories = [
            self._make_story("Market Rally Continues Strong Gains Trading", "Finance"),
            self._make_story("Climate Report Shows Warming Trend Increase", "Climate"),
        ]

        batch_call_count = [0]
        single_call_count = [0]

        async def side_effect(**kwargs):
            batch_call_count[0] += 1
            msgs = kwargs.get("messages", [])
            system = msgs[0]["content"] if msgs else ""
            if "BATCH" in system or "batch" in system.lower():
                content = (
                    "STORY_0 | Market rally continues=Market rally continued with strong gains today. Stocks surged.\n"
                    "STORY_1 | Climate report warming=Climate report shows warming trend with temperature increase."
                )
                r = mock.MagicMock()
                r.choices = [mock.MagicMock(message=mock.MagicMock(content=content))]
                return r
            else:
                single_call_count[0] += 1
                r = mock.MagicMock()
                r.choices = [
                    mock.MagicMock(
                        message=mock.MagicMock(content="Single story fallback summary text here.")
                    )
                ]
                return r

        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 2):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", [0.01]):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await batch_summarize_all(client, stories)

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertTrue(batch_call_count[0] > 0 or single_call_count[0] > 0)

    def test_batch_summarize_all_sub_batches_and_error(self):
        stories = [
            self._make_story("Story A Finance", "Finance"),
            self._make_story("Story B Finance", "Finance"),
            self._make_story("Story C Finance", "Finance"),
            self._make_story("Story D Finance", "Finance"),
        ]

        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=Exception("API error"))

        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await batch_summarize_all(client, stories)

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result.total_stories, 4)


class TestBatchTopicMismatchRejection(TestCase):
    """v1.0.112: topic-mismatched summaries are rejected in batch path."""

    def _make_story(self, title, category, context=None, snippet=None):

        s = StoryPipelineState(title, "http://x", snippet or "", "2024-01-01", category)
        s.context = context or f"Context for {title}." * 5
        s.summary = None
        return s

    def test_batch_rejects_topic_mismatch(self):
        """Batch summary with zero shared keywords with headline is rejected → fallback to [Auto]."""
        stories = [
            self._make_story(
                "Houston weather has been stuck on repeat — but not for much longer", "Weather"
            ),
        ]

        async def side_effect(**kwargs):
            # LLM returns a topic-mismatched summary
            r = mock.MagicMock()
            r.choices = [
                mock.MagicMock(
                    message=mock.MagicMock(
                        content="STORY_0 | temperatures gulf=average temperatures in the Gulf region could lead to stronger storms. Residents should prepare for the return of rain chances this weekend."
                    )
                )
            ]
            return r

        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await batch_summarize_all(client, stories, batch_size=1)

        result = asyncio.get_event_loop().run_until_complete(_run())
        # Topic-mismatched summary should be rejected; fall back to [Auto]
        self.assertTrue(stories[0].summary.startswith("[Auto]"))

    def test_batch_accepts_topic_aligned(self):
        """Batch summary with shared keywords is accepted normally."""
        stories = [
            self._make_story("Houston weather has been stuck on repeat", "Weather"),
        ]

        async def side_effect(**kwargs):
            r = mock.MagicMock()
            r.choices = [
                mock.MagicMock(
                    message=mock.MagicMock(
                        content="STORY_0 | Houston weather repeat=Houston weather has been stuck in a hot pattern for weeks. Conditions are expected to change this weekend with rain chances returning."
                    )
                )
            ]
            return r

        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await batch_summarize_all(client, stories, batch_size=1)

        result = asyncio.get_event_loop().run_until_complete(_run())
        # Topic-aligned summary should be accepted
        self.assertFalse(stories[0].summary.startswith("[Auto]"))
        self.assertNotEqual(stories[0].summary, "")


class TestBatchSchedulerControls(TestCase):
    """Batch size and concurrency controls (Perf-7 benchmark)."""

    def _make_story(self, title, category, snippet=None):

        s = StoryPipelineState(title, "http://x", snippet or "", "2024-01-01", category)
        s.context = f"Context for {title} with enough text for testing." * 3
        s.summary = None
        return s

    def test_custom_batch_size_split(self):
        """batch_size=2 splits 4 stories into 2 sub-batches instead of 2 (3+1)."""
        stories = [
            self._make_story("Story A Finance", "Finance"),
            self._make_story("Story B Finance", "Finance"),
            self._make_story("Story C Finance", "Finance"),
            self._make_story("Story D Finance", "Finance"),
        ]

        call_count = [0]

        async def side_effect(**kwargs):
            call_count[0] += 1
            user_content = kwargs["messages"][1]["content"]
            # Extract story lines from batch to know which headlines are in this batch
            blocks = user_content.split("\n---\n\n")
            batch_headlines = []
            for block in blocks:
                for line in block.strip().split("\n"):
                    if line and not line.startswith(("1. ", "2. ", "3. ")):
                        batch_headlines.append(line.strip())
                        break

            parts = []
            for i, hl in enumerate(batch_headlines):
                parts.append(
                    f"STORY_{i} | {hl}=Finance market summary for {hl}. Detailed analysis follows with more text."
                )
            content = "\n".join(parts)
            r = mock.MagicMock()
            r.choices = [mock.MagicMock(message=mock.MagicMock(content=content))]
            return r

        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await batch_summarize_all(client, stories, batch_size=2)

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(call_count[0], 2)  # 4 stories / batch_size 2 = 2 batches
        self.assertTrue(all(s.summary and "market summary" in s.summary for s in stories))

    def test_concurrency_1_serial(self):
        """max_concurrency=1 (default) runs sub-batches serially."""
        stories = [
            self._make_story("Tech A", "Tech"),
            self._make_story("Tech B", "Tech"),
            self._make_story("News A", "News"),
            self._make_story("News B", "News"),
        ]

        active = [0]
        max_active = [0]

        async def side_effect(**kwargs):
            active[0] += 1
            max_active[0] = max(max_active[0], active[0])
            await asyncio.sleep(0.05)
            user_content = kwargs["messages"][1]["content"]
            blocks = user_content.split("\n---\n\n")
            batch_headlines = []
            for block in blocks:
                for line in block.strip().split("\n"):
                    if line and not line.startswith(("1. ", "2. ", "3. ")):
                        batch_headlines.append(line.strip())
                        break
            parts = []
            for i, hl in enumerate(batch_headlines):
                parts.append(
                    f"STORY_{i} | {hl}=Serial summary for {hl}. Detail text with more sentences here."
                )
            r = mock.MagicMock()
            r.choices = [mock.MagicMock(message=mock.MagicMock(content="\n".join(parts)))]
            active[0] -= 1
            return r

        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await batch_summarize_all(client, stories, batch_size=2)

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(max_active[0], 1)  # Only 1 concurrent
        self.assertTrue(all(s.summary and "Serial summary" in s.summary for s in stories))

    def test_subbatch_exception_isolation(self):
        """When one sub-batch raises an exception, other batches still complete."""
        stories = [
            self._make_story("Tech A", "Tech"),
            self._make_story("Tech B", "Tech"),
            self._make_story("News A", "News"),
            self._make_story("News B", "News"),
        ]

        call_count = [0]

        async def side_effect(**kwargs):
            call_count[0] += 1
            user_content = kwargs["messages"][1]["content"]
            if "Tech" in user_content:
                raise RuntimeError("Tech batch failed")
            blocks = user_content.split("\n---\n\n")
            batch_headlines = []
            for block in blocks:
                for line in block.strip().split("\n"):
                    if line and not line.startswith(("1. ", "2. ", "3. ")):
                        batch_headlines.append(line.strip())
                        break
            parts = []
            for i, hl in enumerate(batch_headlines):
                parts.append(
                    f"STORY_{i} | {hl}=News summary for {hl}. Detail here with more text."
                )
            r = mock.MagicMock()
            r.choices = [mock.MagicMock(message=mock.MagicMock(content="\n".join(parts)))]
            return r

        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        with mock.patch(
                            "daily_brief.llm.summarizer._summarize",
                            new_callable=AsyncMock,
                            return_value=None,
                        ):
                            return await batch_summarize_all(client, stories, batch_size=2)

        result = asyncio.get_event_loop().run_until_complete(_run())
        # Tech stories should have empty/fallback summary (batch failed, LLM retry also failed)
        self.assertTrue(not stories[0].summary or stories[0].summary.startswith("[Auto]"))
        self.assertTrue(not stories[1].summary or stories[1].summary.startswith("[Auto]"))
        # News stories should have valid summary
        self.assertIn("News summary", stories[2].summary)
        self.assertIn("News summary", stories[3].summary)
