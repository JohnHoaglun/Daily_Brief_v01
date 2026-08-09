"""
Unit tests for daily_brief/llm/summarizer.py.
"""
import asyncio
from unittest import TestCase, mock
from unittest.mock import AsyncMock, MagicMock

from daily_brief.llm.summarizer import (
    _is_refusal,
    _is_boilerplate,
    _is_valid_summary,
    StoryPipelineState,
    _generate_auto_fallback,
    _summarize,
    _has_topic_overlap,
)


# ---------------------------------------------------------------------------
# 1.  _is_refusal
# ---------------------------------------------------------------------------

class TestIsRefusal(TestCase):
    """Detects LLM refusal / placeholder text."""

    def test_refusal_markers(self):
        self.assertTrue(_is_refusal("Please provide the article text for summarization."))
        self.assertTrue(_is_refusal("I don't have access to the full article content."))
        self.assertTrue(_is_refusal("I cannot summarize this without the source text."))

    def test_factual_not_refusal(self):
        self.assertFalse(_is_refusal("The Federal Reserve raised interest rates by 0.25% today."))
        self.assertFalse(_is_refusal("Houston city council approved a new transit plan last night."))

    def test_empty_returns_false(self):
        self.assertFalse(_is_refusal(""))
        self.assertFalse(_is_refusal(None))


# ---------------------------------------------------------------------------
# 3.  _is_boilerplate
# ---------------------------------------------------------------------------

class TestIsBoilerplate(TestCase):
    """Detects vague, generic boilerplate summaries."""

    def test_boilerplate_markers(self):
        self.assertTrue(_is_boilerplate("This highlights a significant trend in modern technology."))
        self.assertTrue(_is_boilerplate("This article discusses the implications of the new policy."))

    def test_case_insensitive(self):
        self.assertTrue(_is_boilerplate("This Highlights A Significant discovery."))
        self.assertTrue(_is_boilerplate("this article discusses climate change in depth."))

    def test_factual_not_boilerplate(self):
        self.assertFalse(_is_boilerplate("NASA launched the Artemis II mission yesterday morning."))
        self.assertFalse(_is_boilerplate("Texas Governor signed SB 123 into law, allocating $2B for infrastructure."))


# ---------------------------------------------------------------------------
# 4.  _generate_auto_fallback
# ---------------------------------------------------------------------------

class TestGenerateAutoFallback(TestCase):
    """Deterministic fallback summary from title."""

    def test_auto_format(self):
        result = _generate_auto_fallback("Houston Floods Hit Record Levels")
        self.assertEqual(result, "[Auto] Houston Floods Hit Record Levels")

    def test_trailing_colon_cleaned(self):
        result = _generate_auto_fallback("Houston Floods Hit Record Levels:")
        self.assertEqual(result, "[Auto] Houston Floods Hit Record Levels")

    def test_none_title_returns_unavailable(self):
        result = _generate_auto_fallback(None)
        self.assertEqual(result, "[Summary Unavailable]")

    def test_empty_title_returns_unavailable(self):
        result = _generate_auto_fallback("")
        self.assertEqual(result, "[Summary Unavailable]")

    def test_extra_whitespace_cleaned(self):
        result = _generate_auto_fallback("  Extra   Spaces  Here  ")
        self.assertEqual(result, "[Auto] Extra Spaces Here")


# ---------------------------------------------------------------------------
# 5.  _summarize (mocked client)
# ---------------------------------------------------------------------------

class TestSummarize(TestCase):
    """_summarize with mocked async LLM client (Perf-8)."""

    def _make_client(self, response_text):
        client = mock.MagicMock()
        msg = mock.MagicMock()
        msg.content = response_text
        msg.message = msg
        choice = mock.MagicMock()
        choice.message = msg
        choice.choices = [choice]
        client.chat_completions_create = AsyncMock(return_value=choice)
        return client

    def test_successful_single_call(self):
        client = self._make_client("The Fed raised rates by 0.25 percent Wednesday.")
        async def _run():
            return await _summarize(client, "Some context text that is long enough to be meaningful for the LLM to process and summarize properly.", title="Test", min_chars=0)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "The Fed raised rates by 0.25 percent Wednesday.")

    def test_empty_response_triggers_retry_then_fallback(self):
        call_count = [0]
        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                r = mock.MagicMock()
                r.choices = [mock.MagicMock(message=mock.MagicMock(content=""))]
                return r
            else:
                r = mock.MagicMock()
                r.choices = [mock.MagicMock(message=mock.MagicMock(content="Valid summary text."))]
                return r
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)
        async def _run():
            with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_ATTEMPTS", 2):
                with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_BACKOFF", [0.01, 0.02]):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await _summarize(client, "Context text long enough for processing.", title="Test Title", min_chars=0)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "Valid summary text.")

    def test_llm_exception_triggers_fallback(self):
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=Exception("Connection refused"))
        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await _summarize(client, "Context text that is long enough to be meaningful.", title="Error Title", min_chars=0)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIn("[Auto]", result)

    def test_title_based_fallback_when_exhausted(self):
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=Exception("Down"))
        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 2):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", [0.01, 0.02]):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await _summarize(client, "Enough context here to process.", title="My Headline", min_chars=0)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "[Auto] My Headline")

    def test_none_title_fallback_unavailable(self):
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=Exception("Down"))
        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await _summarize(client, "Enough context here.", title=None, min_chars=0)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "[Summary Unavailable]")

    def test_summarize_context_too_short(self):
        client = mock.MagicMock()
        async def _run():
            return await _summarize(client, "hi", title="Title", min_chars=100)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIsNone(result)

    def test_summarize_boilerplate_retry(self):
        call_count = [0]
        async def side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                r = mock.MagicMock()
                r.choices = [mock.MagicMock(message=mock.MagicMock(
                    content="This article discusses the implications of the new policy thoroughly."
                ))]
                return r
            else:
                r = mock.MagicMock()
                r.choices = [mock.MagicMock(message=mock.MagicMock(
                    content="The Fed raised rates by 0.25 percent. Bond yields climbed sharply. Treasury prices fell."
                ))]
                return r
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)
        async def _run():
            with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_ATTEMPTS", 2):
                with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_BACKOFF", [0.01, 0.02]):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await _summarize(client, "Some context text that is long enough to be meaningful for the LLM to process.", title="Test", min_chars=0)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIn("Fed", result)
        self.assertEqual(call_count[0], 2)


# ---------------------------------------------------------------------------
# _is_valid_summary (quality gate)
# ---------------------------------------------------------------------------

class TestIsValidSummary(TestCase):
    """Quality gate: empty/None/refusal/boilerplate/one-sentence/headline echo/topic mismatch."""

    def test_empty_summary_rejected(self):
        self.assertFalse(_is_valid_summary("", "Any headline"))

    def test_none_summary_rejected(self):
        self.assertFalse(_is_valid_summary(None, "Any headline"))

    def test_one_sentence_rejected(self):
        self.assertFalse(
            _is_valid_summary(
                "Houston weather will change this weekend.",
                "Houston weather has been stuck on repeat",
            )
        )

    def test_headline_exact_echo_rejected(self):
        self.assertFalse(
            _is_valid_summary(
                "Houston weather update",
                "Houston weather update",
            )
        )

    def test_headline_plus_period_rejected(self):
        self.assertFalse(
            _is_valid_summary(
                "Houston weather update. The summary adds nothing new.",
                "Houston weather update",
            )
        )

    def test_refusal_rejected(self):
        self.assertFalse(
            _is_valid_summary(
                "I cannot summarize this article. I did not have access to the full content.",
                "Houston weather has been stuck on repeat",
            )
        )

    def test_refusal_with_headline_words_rejected(self):
        self.assertFalse(
            _is_valid_summary(
                "I cannot summarize this article about Houston weather. I did not have access.",
                "Houston weather has been stuck on repeat",
            )
        )

    def test_auto_fallback_marker_rejected(self):
        self.assertFalse(
            _is_valid_summary(
                "[Auto] Houston weather repeats through the weekend",
                "Houston weather has been stuck on repeat",
            )
        )

    def test_summary_unavailable_rejected(self):
        self.assertFalse(
            _is_valid_summary(
                "[Summary Unavailable]",
                "Houston weather has been stuck on repeat",
            )
        )

    def test_boilerplate_rejected(self):
        self.assertFalse(
            _is_valid_summary(
                "This article discusses the implications of the new policy in detail. Further analysis is required.",
                "Houston weather has been stuck on repeat",
            )
        )

    def test_topic_mismatch_rejected(self):
        self.assertFalse(
            _is_valid_summary(
                "average temperatures in the Gulf region could lead to stronger storms. Residents should prepare for the return of rain chances this weekend.",
                "Houston weather has been stuck on repeat — but not for much longer",
            )
        )

    def test_topic_match_accepted(self):
        self.assertTrue(
            _is_valid_summary(
                "Houston weather has been stuck in a hot pattern for weeks. Conditions are expected to change this weekend with rain chances returning.",
                "Houston weather has been stuck on repeat — but not for much longer",
            )
        )

    def test_valid_two_sentence_passes(self):
        self.assertTrue(
            _is_valid_summary(
                "Houston weather has been stuck in a hot pattern. Conditions are expected to change this weekend.",
                "Houston weather has been stuck on repeat",
            )
        )

    def test_topic_overlap_passes(self):
        self.assertTrue(
            _has_topic_overlap(
                "Houston weather has been repeating for weeks.",
                "Houston weather has been stuck on repeat — but not for much longer",
            )
        )

    def test_topic_overlap_fails_zero_words(self):
        self.assertFalse(
            _has_topic_overlap(
                "average temperatures in the Gulf region could lead to stronger storms",
                "Stock market crashes as tech companies report record losses",
            )
        )

    def test_stop_words_filtered(self):
        from daily_brief.llm.summarizer import _significant_words
        words = _significant_words("The and of is was are be been this that as")
        self.assertEqual(words, set())

    def test_significant_words_extracted(self):
        from daily_brief.llm.summarizer import _significant_words
        words = _significant_words("Houston weather has been stuck on repeat")
        self.assertIn("houston", words)
        self.assertIn("weather", words)
        self.assertIn("repeat", words)


# ---------------------------------------------------------------------------
# batch_summarize_all
# ---------------------------------------------------------------------------

class TestBatchSummarizeAll(TestCase):
    """batch_summarize_all integration with mocked async client (Perf-8)."""

    def _make_story(self, title, category, context=None, snippet=None):
        from daily_brief.llm.summarizer import StoryPipelineState
        s = StoryPipelineState(title, "http://x", snippet or "", "2024-01-01", category)
        s.context = context
        s.summary = None
        return s

    def test_batch_summarize_all_empty(self):
        from daily_brief.llm.summarizer import batch_summarize_all
        client = mock.MagicMock()
        async def _run():
            return await batch_summarize_all(client, [])
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result.total_stories, 0)

    def test_batch_summarize_all_with_retries(self):
        from daily_brief.config import SYSTEM_BATCH_PROMPT
        from daily_brief.llm.summarizer import batch_summarize_all

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
                r.choices = [mock.MagicMock(message=mock.MagicMock(content="Single story fallback summary text here."))]
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
        from daily_brief.llm.summarizer import batch_summarize_all

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
        from daily_brief.llm.summarizer import StoryPipelineState
        s = StoryPipelineState(title, "http://x", snippet or "", "2024-01-01", category)
        s.context = context or f"Context for {title}." * 5
        s.summary = None
        return s

    def test_batch_rejects_topic_mismatch(self):
        """Batch summary with zero shared keywords with headline is rejected → fallback to [Auto]."""
        from daily_brief.llm.summarizer import batch_summarize_all

        stories = [
            self._make_story("Houston weather has been stuck on repeat — but not for much longer", "Weather"),
        ]

        async def side_effect(**kwargs):
            # LLM returns a topic-mismatched summary
            r = mock.MagicMock()
            r.choices = [mock.MagicMock(message=mock.MagicMock(
                content="STORY_0 | temperatures gulf=average temperatures in the Gulf region could lead to stronger storms. Residents should prepare for the return of rain chances this weekend."
            ))]
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
        from daily_brief.llm.summarizer import batch_summarize_all

        stories = [
            self._make_story("Houston weather has been stuck on repeat", "Weather"),
        ]

        async def side_effect(**kwargs):
            r = mock.MagicMock()
            r.choices = [mock.MagicMock(message=mock.MagicMock(
                content="STORY_0 | Houston weather repeat=Houston weather has been stuck in a hot pattern for weeks. Conditions are expected to change this weekend with rain chances returning."
            ))]
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
        from daily_brief.llm.summarizer import StoryPipelineState
        s = StoryPipelineState(title, "http://x", snippet or "", "2024-01-01", category)
        s.context = f"Context for {title} with enough text for testing." * 3
        s.summary = None
        return s

    def test_custom_batch_size_split(self):
        """batch_size=2 splits 4 stories into 2 sub-batches instead of 2 (3+1)."""
        from daily_brief.llm.summarizer import batch_summarize_all

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
                parts.append(f"STORY_{i} | {hl}=Finance market summary for {hl}. Detailed analysis follows with more text.")
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
        from daily_brief.llm.summarizer import batch_summarize_all

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
                parts.append(f"STORY_{i} | {hl}=Serial summary for {hl}. Detail text with more sentences here.")
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
        from daily_brief.llm.summarizer import batch_summarize_all

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
                parts.append(f"STORY_{i} | {hl}=News summary for {hl}. Detail here with more text.")
            r = mock.MagicMock()
            r.choices = [mock.MagicMock(message=mock.MagicMock(content="\n".join(parts)))]
            return r

        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                            return await batch_summarize_all(client, stories, batch_size=2)

        result = asyncio.get_event_loop().run_until_complete(_run())
        # Tech stories should have empty/fallback summary (batch failed, LLM retry also failed)
        self.assertTrue(not stories[0].summary or stories[0].summary.startswith("[Auto]"))
        self.assertTrue(not stories[1].summary or stories[1].summary.startswith("[Auto]"))
        # News stories should have valid summary
        self.assertIn("News summary", stories[2].summary)
        self.assertIn("News summary", stories[3].summary)
