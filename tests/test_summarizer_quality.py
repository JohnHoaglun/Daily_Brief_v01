"""
Quality/single-call unit tests for daily_brief/llm/summarizer.py.
Split from test_summarizer.py.
"""

import asyncio
from unittest import TestCase, mock
from unittest.mock import AsyncMock

from daily_brief.llm.summarizer import (
    StoryPipelineState,
    _generate_auto_fallback,
    _has_topic_overlap,
    _is_boilerplate,
    _is_refusal,
    _is_valid_summary,
    _summarize,
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
        self.assertFalse(
            _is_refusal("Houston city council approved a new transit plan last night.")
        )

    def test_empty_returns_false(self):
        self.assertFalse(_is_refusal(""))
        self.assertFalse(_is_refusal(None))


# ---------------------------------------------------------------------------
# 3.  _is_boilerplate
# ---------------------------------------------------------------------------


class TestIsBoilerplate(TestCase):
    """Detects vague, generic boilerplate summaries."""

    def test_boilerplate_markers(self):
        self.assertTrue(
            _is_boilerplate("This highlights a significant trend in modern technology.")
        )
        self.assertTrue(
            _is_boilerplate("This article discusses the implications of the new policy.")
        )

    def test_case_insensitive(self):
        self.assertTrue(_is_boilerplate("This Highlights A Significant discovery."))
        self.assertTrue(_is_boilerplate("this article discusses climate change in depth."))

    def test_factual_not_boilerplate(self):
        self.assertFalse(
            _is_boilerplate("NASA launched the Artemis II mission yesterday morning.")
        )
        self.assertFalse(
            _is_boilerplate(
                "Texas Governor signed SB 123 into law, allocating $2B for infrastructure."
            )
        )


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
            return await _summarize(
                client,
                "Some context text that is long enough to be meaningful for the LLM to process and summarize properly.",
                title="Test",
                min_chars=0,
            )

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
                        return await _summarize(
                            client,
                            "Context text long enough for processing.",
                            title="Test Title",
                            min_chars=0,
                        )

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "Valid summary text.")

    def test_llm_exception_triggers_fallback(self):
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=Exception("Connection refused"))

        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await _summarize(
                            client,
                            "Context text that is long enough to be meaningful.",
                            title="Error Title",
                            min_chars=0,
                        )

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIn("[Auto]", result)

    def test_title_based_fallback_when_exhausted(self):
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=Exception("Down"))

        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 2):
                with mock.patch(
                    "daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", [0.01, 0.02]
                ):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await _summarize(
                            client,
                            "Enough context here to process.",
                            title="My Headline",
                            min_chars=0,
                        )

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "[Auto] My Headline")

    def test_none_title_fallback_unavailable(self):
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=Exception("Down"))

        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await _summarize(
                            client, "Enough context here.", title=None, min_chars=0
                        )

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
                r.choices = [
                    mock.MagicMock(
                        message=mock.MagicMock(
                            content="This article discusses the implications of the new policy thoroughly."
                        )
                    )
                ]
                return r
            else:
                r = mock.MagicMock()
                r.choices = [
                    mock.MagicMock(
                        message=mock.MagicMock(
                            content="The Fed raised rates by 0.25 percent. Bond yields climbed sharply. Treasury prices fell."
                        )
                    )
                ]
                return r

        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)

        async def _run():
            with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_ATTEMPTS", 2):
                with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_BACKOFF", [0.01, 0.02]):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await _summarize(
                            client,
                            "Some context text that is long enough to be meaningful for the LLM to process.",
                            title="Test",
                            min_chars=0,
                        )

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
