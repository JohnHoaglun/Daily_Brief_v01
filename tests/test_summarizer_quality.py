"""Quality/single-call unit tests for daily_brief/llm/summarizer.py — compact."""

import asyncio
from unittest import TestCase, mock
from unittest.mock import AsyncMock

from daily_brief.llm.summarizer import (
    _generate_auto_fallback,
    _is_boilerplate,
    _is_refusal,
    _is_valid_summary,
    _summarize,
)


class TestCoreHelpers(TestCase):
    """_is_refusal / _is_boilerplate / _generate_auto_fallback."""

    def test_refusal_and_boilerplate_and_fallback(self):
        self.assertTrue(_is_refusal("I cannot summarize this without the source text."))
        self.assertFalse(_is_refusal("The Federal Reserve raised interest rates by 0.25%."))
        self.assertTrue(_is_boilerplate("This article discusses the implications of the new policy."))
        self.assertFalse(_is_boilerplate("NASA launched the Artemis II mission yesterday."))
        self.assertEqual(_generate_auto_fallback("Houston Floods Hit Record"), "[Auto] Houston Floods Hit Record")
        self.assertEqual(_generate_auto_fallback(""), "[Summary Unavailable]")
        self.assertEqual(_generate_auto_fallback(None), "[Summary Unavailable]")
        self.assertEqual(_generate_auto_fallback("Title:"), "[Auto] Title")


class TestSummarize(TestCase):
    """_summarize with mocked async LLM client."""

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
        client = self._make_client("The Fed raised rates by 0.25 percent.")
        async def _run():
            return await _summarize(client, "Long context text for summarization processing.", title="Test", min_chars=0)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "The Fed raised rates by 0.25 percent.")

    def test_llm_exception_triggers_fallback(self):
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=Exception("Down"))
        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await _summarize(client, "Context text.", title="Error Title", min_chars=0)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "[Auto] Error Title")

    def test_context_too_short(self):
        client = mock.MagicMock()
        async def _run():
            return await _summarize(client, "hi", title="Title", min_chars=100)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIsNone(result)


class TestIsValidSummary(TestCase):
    """Quality gate: empty/refusal/boilerplate/headline-echo/topic mismatch."""

    def test_valid_summary_accepted(self):
        self.assertTrue(
            _is_valid_summary(
                "Houston weather has been stuck in a hot pattern for weeks. Conditions are expected to change.",
                "Houston weather has been stuck on repeat",
            )
        )

    def test_summary_rejected(self):
        """Topics must overlap, not be one-sentence, not be headline echo/refusal/boilerplate/auto/unavailable."""
        rejected = [
            ("", "H"),
            (None, "H"),
            ("One sentence.", "Houston weather"),
            ("Houston weather update.", "Houston weather"),
            ("I cannot summarize this article about Houston.", "H"),
            ("[Auto] Houston weather.", "H"),
            ("[Summary Unavailable]", "H"),
            ("This article discusses the implications of the new policy. Further analysis needed.", "H"),
            ("Gulf region temperatures lead to storms. Residents prepare.", "Houston weather"),
        ]
        for summary, headline in rejected:
            self.assertFalse(_is_valid_summary(summary, headline))


class TestSignificantWords(TestCase):
    def test_stop_words_filtered_and_extracted(self):
        from daily_brief.llm.summarizer import _significant_words
        self.assertEqual(_significant_words("The and of is was are"), set())
        words = _significant_words("Houston weather has been stuck on repeat")
        self.assertIn("houston", words)
        self.assertIn("weather", words)
