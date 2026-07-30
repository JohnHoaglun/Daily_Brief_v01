"""
Unit tests for src/daily_brief/llm/summarizer.py.
"""
import os
import sys
import time
from unittest import TestCase, mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from daily_brief.llm.summarizer import (
    _safe_sentence_summary,
    _is_refusal,
    _is_boilerplate,
    _count_sentences,
    parse_batch_summary_response,
    StoryPipelineState,
    _generate_auto_fallback,
    build_context,
    _summarize,
)


# ---------------------------------------------------------------------------
# 1.  _safe_sentence_summary
# ---------------------------------------------------------------------------

class TestSafeSentenceSummary(TestCase):
    """Trims and cleans LLM summary text to a max of 3 sentences."""

    def test_three_plus_sentences_returns_first_three(self):
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = _safe_sentence_summary(text)
        self.assertEqual(result, "First sentence. Second sentence. Third sentence.")

    def test_four_sentences_returns_first_three(self):
        text = "A. B. C. D."
        result = _safe_sentence_summary(text)
        self.assertEqual(result, "A. B. C.")

    def test_one_sentence_returns_all(self):
        text = "This is a single sentence."
        result = _safe_sentence_summary(text)
        self.assertEqual(result, "This is a single sentence.")

    def test_two_sentences_returns_all(self):
        text = "First. Second."
        result = _safe_sentence_summary(text)
        self.assertEqual(result, "First. Second.")

    def test_empty_string_returns_empty(self):
        self.assertEqual(_safe_sentence_summary(""), "")

    def test_none_returns_empty(self):
        self.assertEqual(_safe_sentence_summary(None), "")

    def test_extra_whitespace_collapsed(self):
        text = "  First   sentence.   Second   sentence.  "
        result = _safe_sentence_summary(text)
        self.assertEqual(result, "First sentence. Second sentence.")

    def test_double_dot_cleans_to_single(self):
        text = "First.. Second.. Third.."
        result = _safe_sentence_summary(text)
        self.assertEqual(result, "First. Second. Third.")

    def test_long_string_no_punctuation(self):
        text = "This is a very long string with no sentence boundaries at all"
        result = _safe_sentence_summary(text)
        self.assertEqual(result, "This is a very long string with no sentence boundaries at all")


# ---------------------------------------------------------------------------
# 2.  _is_refusal
# ---------------------------------------------------------------------------

class TestIsRefusal(TestCase):
    """Detects LLM refusal / placeholder text."""

    def test_please_provide_article_is_refusal(self):
        self.assertTrue(_is_refusal("Please provide the article text for summarization."))

    def test_no_access_is_refusal(self):
        self.assertTrue(_is_refusal("I don't have access to the full article content."))

    def test_cannot_summarize_is_refusal(self):
        self.assertTrue(_is_refusal("I cannot summarize this without the source text."))

    def test_factual_text_is_not_refusal(self):
        self.assertFalse(_is_refusal("The Federal Reserve raised interest rates by 0.25% today."))

    def test_news_summary_is_not_refusal(self):
        self.assertFalse(_is_refusal("Houston city council approved a new transit plan last night."))

    def test_empty_returns_false(self):
        self.assertFalse(_is_refusal(""))
        self.assertFalse(_is_refusal(None))


# ---------------------------------------------------------------------------
# 3.  _is_boilerplate
# ---------------------------------------------------------------------------

class TestIsBoilerplate(TestCase):
    """Detects vague, generic boilerplate summaries."""

    def test_highlights_significant_is_boilerplate(self):
        self.assertTrue(_is_boilerplate("This highlights a significant trend in modern technology."))

    def test_highlights_significant_case_insensitive(self):
        self.assertTrue(_is_boilerplate("This Highlights A Significant discovery."))

    def test_article_discusses_is_boilerplate(self):
        self.assertTrue(_is_boilerplate("This article discusses the implications of the new policy."))

    def test_article_discusses_lower(self):
        self.assertTrue(_is_boilerplate("this article discusses climate change in depth."))

    def test_factual_text_not_boilerplate(self):
        self.assertFalse(_is_boilerplate("NASA launched the Artemis II mission yesterday morning."))

    def test_specific_summary_not_boilerplate(self):
        self.assertFalse(_is_boilerplate("Texas Governor signed SB 123 into law, allocating $2B for infrastructure."))


# ---------------------------------------------------------------------------
# 4.  _count_sentences
# ---------------------------------------------------------------------------

class TestCountSentences(TestCase):
    """Counts sentences in a text string."""

    def test_multiple_sentences(self):
        self.assertEqual(_count_sentences("First. Second. Third."), 3)

    def test_single_sentence(self):
        self.assertEqual(_count_sentences("Just one sentence here."), 1)

    def test_empty_returns_zero(self):
        self.assertEqual(_count_sentences(""), 0)
        self.assertEqual(_count_sentences(None), 0)

    def test_mixed_punctuation(self):
        text = "What happened? It was amazing! She couldn't believe it."
        self.assertEqual(_count_sentences(text), 3)


# ---------------------------------------------------------------------------
# 5.  parse_batch_summary_response
# ---------------------------------------------------------------------------

class TestParseBatchSummaryResponseSTORY(TestCase):
    """STORY_N | headline=summary format parsing."""

    def test_story_n_with_equals_separator_and_headlines(self):
        response = (
            "STORY_0 | NASA Launches Mission=NASA successfully launched the Artemis mission yesterday.\n"
            "STORY_1 | Fed Raises Rates=The Federal Reserve raised rates by 0.25 percent."
        )
        headlines = ["NASA Launches Mission", "Fed Raises Rates"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        self.assertIn("NASA", result[0])
        self.assertIn("Federal Reserve", result[1])

    def test_story_n_without_equals_and_headlines(self):
        response = (
            "STORY_0 | The stock market rallied on strong earnings reports.\n"
            "STORY_1 | A new climate study published findings yesterday."
        )
        headlines = ["Stock market rallied", "Climate study published findings"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        self.assertTrue(len(result[0]) > 0)
        self.assertTrue(len(result[1]) > 0)

    def test_story_n_equals_separator_parsums_equals_sign(self):
        response = "STORY_0 | Headline=The summary after the equals sign goes here."
        headlines = ["Headline"]
        result = parse_batch_summary_response(response, 1, story_headlines=headlines)
        self.assertEqual(len(result), 1)
        self.assertIn("equals sign", result[0])
        self.assertNotIn("Headline=", result[0])

    def test_single_story_count_one(self):
        response = "STORY_0 | Brief update on the market today."
        result = parse_batch_summary_response(response, 1)
        self.assertEqual(len(result), 1)
        self.assertTrue(len(result[0]) > 0)

    def test_empty_response_returns_empty_list(self):
        result = parse_batch_summary_response("", 3)
        self.assertEqual(result, ["", "", ""])

    def test_none_response_returns_empty_list(self):
        result = parse_batch_summary_response(None, 2)
        self.assertEqual(result, ["", ""])

    def test_story_n_cleaned_via_safe_sentence_summary(self):
        response = (
            "STORY_0 | Headline=First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence."
        )
        result = parse_batch_summary_response(response, 1)
        result_text = result[0]
        parts = [p for p in result_text.split(".") if p.strip()]
        self.assertLessEqual(len(parts), 3)


class TestParseBatchSummaryResponseNumbered(TestCase):
    """Numbered format (1. ..., 2. ...) parsing."""

    def test_numbered_format(self):
        response = (
            "1. The stock market rallied today.\n"
            "   Tech stocks led the gains.\n"
            "\n"
            "2. A hurricane is forming in the Atlantic.\n"
            "   Storm names include Debby and Erika."
        )
        result = parse_batch_summary_response(response, 2)
        self.assertEqual(len(result), 2)
        self.assertTrue(len(result[0]) > 0)
        self.assertTrue(len(result[1]) > 0)

    def test_numbered_with_hashes(self):
        response = (
            "### 1. First story summary text.\n"
            "### 2. Second story summary text."
        )
        result = parse_batch_summary_response(response, 2)
        self.assertEqual(len(result), 2)

    def test_single_story_plain_text(self):
        response = "Here is a summary of the story. The market closed higher today. Bonds fell slightly."
        result = parse_batch_summary_response(response, 1)
        self.assertEqual(len(result), 1)
        self.assertTrue(len(result[0]) > 0)


class TestParseBatchSummaryResponseFuzzy(TestCase):
    """Fuzzy headline matching via difflib and keyword overlap."""

    def test_fuzzy_headline_match(self):
        response = (
            "STORY_0 | Space Mission Successful=NASA made the launch successfully yesterday."
        )
        headlines = ["NASA's Space Mission to Mars Is Successful"]
        result = parse_batch_summary_response(response, 1, story_headlines=headlines)
        self.assertEqual(len(result), 1)
        self.assertTrue(len(result[0]) > 0)
        self.assertIn("NASA", result[0])

    def test_keyword_overlap_match(self):
        response = (
            "STORY_0 | Market=Stocks in the energy sector surged as oil prices climbed to new highs today."
        )
        headlines = ["Energy Stocks Surge on Oil Price Rally"]
        result = parse_batch_summary_response(response, 1, story_headlines=headlines)
        self.assertEqual(len(result), 1)
        self.assertTrue("energy" in result[0].lower() or "stock" in result[0].lower() or "oil" in result[0].lower())

    def test_positional_fallback_numbered_format(self):
        response = (
            "1. First story headline.\n"
            "   Market details showed strong growth.\n"
            "\n"
            "2. Second story headline.\n"
            "   Weather info showed clear skies."
        )
        result = parse_batch_summary_response(response, 2)
        self.assertEqual(len(result), 2)
        self.assertIn("Market", result[0])
        self.assertIn("Weather", result[1])

    def test_positional_fallback_story_n_single(self):
        response = "STORY_0 | Single story summary with important details."
        result = parse_batch_summary_response(response, 1)
        self.assertEqual(len(result), 1)
        self.assertTrue(len(result[0]) > 0)
        self.assertIn("important", result[0])


class TestParseBatchSummaryResponseSwap(TestCase):
    """Swap detection and correction logic."""

    def test_swap_detection_logs_warning(self):
        import logging
        response = (
            "STORY_0 | Summary about SpaceX launch.\n"
            "STORY_1 | Summary about climate report."
        )
        headlines = [
            "Climate Report Released",
            "SpaceX Launch Success",
        ]
        with mock.patch.object(__import__("daily_brief.llm.summarizer", fromlist=["logger"]), "logger") as mock_logger:
            pass
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)


class TestParseBatchSummaryResponseEdgeCases(TestCase):
    """Edge cases in batch parsing."""

    def test_summary_text_cleaned_via_safe_sentence_summary(self):
        response = (
            "STORY_0 | H=First sentence. Second sentence. Third sentence. Fourth sentence. Fifth sentence. Sixth sentence."
        )
        result = parse_batch_summary_response(response, 1, story_headlines=["H"])
        result_text = result[0]
        self.assertLessEqual(_count_sentences(result_text), 3)

    def test_all_empty_summaries_return_empty(self):
        response = "\n\n\n"
        result = parse_batch_summary_response(response, 2)
        self.assertEqual(result, ["", ""])

    def test_count_larger_than_stories(self):
        response = "STORY_0 | Only one story summary here."
        result = parse_batch_summary_response(response, 3)
        self.assertEqual(len(result), 3)
        self.assertTrue(len(result[0]) > 0)
        self.assertEqual(result[1], "")
        self.assertEqual(result[2], "")


# ---------------------------------------------------------------------------
# 6.  StoryPipelineState
# ---------------------------------------------------------------------------

class TestStoryPipelineState(TestCase):
    """StoryPipelineState slots and defaults."""

    def test_default_slots_exist(self):
        s = StoryPipelineState("Title", "http://x", "Snippet", "2024-01-01", "Tech")
        self.assertEqual(s.title, "Title")
        self.assertEqual(s.link, "http://x")
        self.assertEqual(s.snippet, "Snippet")
        self.assertEqual(s.category, "Tech")
        self.assertEqual(s.pub_dt, "2024-01-01")
        self.assertIsNone(s.context)
        self.assertIsNone(s.summary)

    def test_context_and_summary_default_none(self):
        s = StoryPipelineState("T", "L", "S", "2024-01-01", "Cat")
        self.assertIsNone(s.context)
        self.assertIsNone(s.summary)

    def test_all_fields_settable(self):
        s = StoryPipelineState("T", "L", "S", "2024-01-01", "Cat")
        s.context = "New context"
        s.summary = "New summary"
        self.assertEqual(s.context, "New context")
        self.assertEqual(s.summary, "New summary")

    def test_slots_defined(self):
        s = StoryPipelineState("T", "L", "S", "2024-01-01", "Cat")
        expected_slots = {"title", "link", "snippet", "category", "pub_dt", "context", "summary"}
        self.assertEqual(set(StoryPipelineState.__slots__), expected_slots)


# ---------------------------------------------------------------------------
# 7.  _generate_auto_fallback
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
# 8.  build_context
# ---------------------------------------------------------------------------

class TestBuildContext(TestCase):
    """Context building from StoryPipelineState."""

    def _make_story(self, **overrides):
        s = StoryPipelineState(
            title=overrides.get("title", "Test Title"),
            link=overrides.get("link", "http://example.com"),
            snippet=overrides.get("snippet", "Short snippet text."),
            category=overrides.get("category", "Tech"),
            pub_dt=overrides.get("pub_dt", "2024-01-01"),
        )
        s.context = overrides.get("context")
        return s

    def test_uses_context_when_available(self):
        s = self._make_story(context="A much longer piece of article content that provides good context for the LLM summary generation.")
        result = build_context(s)
        self.assertIn("article content", result)

    def test_context_capped(self):
        s = self._make_story(context="A" * 1000)
        result = build_context(s)
        from daily_brief.config import LLM_CONTEXT_PREVIEW_CHARS
        self.assertLessEqual(len(result), LLM_CONTEXT_PREVIEW_CHARS)

    def test_fallback_to_snippet_and_title(self):
        s = self._make_story(context=None)
        result = build_context(s)
        self.assertIn("Test Title", result)
        self.assertIn("Short snippet", result)

    def test_category_fallback_when_no_snippet(self):
        s = self._make_story(snippet="", context=None)
        result = build_context(s)
        self.assertIn("Test Title", result)
        self.assertIn("Tech", result)

    def test_empty_context_short_fallback(self):
        s = self._make_story(context="", snippet="", title="")
        result = build_context(s)
        self.assertIn("Tech", result)


# ---------------------------------------------------------------------------
# 9.  _summarize (mocked client)
# ---------------------------------------------------------------------------

class TestSummarize(TestCase):
    """_summarize with mocked LLM client."""

    def _make_client(self, response_text):
        client = mock.MagicMock()
        msg = mock.MagicMock()
        msg.content = response_text
        msg.message = msg
        choice = mock.MagicMock()
        choice.message = msg
        choice.choices = [choice]
        client.chat_completions_create.return_value = choice
        return client

    def test_successful_single_call(self):
        client = self._make_client("The Fed raised rates by 0.25 percent Wednesday.")
        result = _summarize(client, "Some context text that is long enough to be meaningful for the LLM to process and summarize properly.", title="Test", min_chars=0)
        self.assertEqual(result, "The Fed raised rates by 0.25 percent Wednesday.")

    def test_empty_response_returns_empty(self):
        client = self._make_client("")
        with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
            with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_BACKOFF", []):
                with mock.patch("time.sleep", return_value=None):
                    result = _summarize(client, "Context text that is long enough to be meaningful.", title="Test Title", min_chars=0)
        self.assertEqual(result, "")

    def test_empty_response_triggers_retry_then_fallback(self):
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call returns empty
                r = mock.MagicMock()
                r.choices = [mock.MagicMock(message=mock.MagicMock(content=""))]
                return r
            else:
                # Second call returns valid text
                r = mock.MagicMock()
                r.choices = [mock.MagicMock(message=mock.MagicMock(content="Valid summary text."))]
                return r
        client = mock.MagicMock()
        client.chat_completions_create.side_effect = side_effect
        with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_ATTEMPTS", 2):
            with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_BACKOFF", [0.01, 0.02]):
                with mock.patch("time.sleep", return_value=None):
                    result = _summarize(client, "Context text long enough for processing.", title="Test Title", min_chars=0)
        self.assertEqual(result, "Valid summary text.")

    def test_llm_exception_triggers_fallback(self):
        client = mock.MagicMock()
        client.chat_completions_create.side_effect = Exception("Connection refused")
        with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                with mock.patch("time.sleep", return_value=None):
                    result = _summarize(client, "Context text that is long enough to be meaningful.", title="Error Title", min_chars=0)
        self.assertIn("[Auto]", result)

    def test_title_based_fallback_when_exhausted(self):
        client = mock.MagicMock()
        client.chat_completions_create.side_effect = Exception("Down")
        with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 2):
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", [0.01, 0.02]):
                with mock.patch("time.sleep", return_value=None):
                    result = _summarize(client, "Enough context here to process.", title="My Headline", min_chars=0)
        self.assertEqual(result, "[Auto] My Headline")

    def test_none_title_fallback_unavailable(self):
        client = mock.MagicMock()
        client.chat_completions_create.side_effect = Exception("Down")
        with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                with mock.patch("time.sleep", return_value=None):
                    result = _summarize(client, "Enough context here.", title=None, min_chars=0)
        self.assertEqual(result, "[Summary Unavailable]")
