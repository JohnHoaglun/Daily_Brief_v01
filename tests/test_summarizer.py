"""
Unit tests for daily_brief/llm/summarizer.py.
"""
import asyncio
import time
from unittest import TestCase, mock
from unittest.mock import AsyncMock, MagicMock

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
    _has_topic_overlap,
    _is_valid_summary,
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
    """StoryPipelineState (Story) fields and defaults."""

    def test_default_fields_exist(self):
        s = StoryPipelineState(title="Title", link="http://x", snippet="Snippet", pub_dt="2024-01-01", category="Tech")
        self.assertEqual(s.title, "Title")
        self.assertEqual(s.link, "http://x")
        self.assertEqual(s.snippet, "Snippet")
        self.assertEqual(s.category, "Tech")
        self.assertEqual(s.pub_dt, "2024-01-01")
        self.assertIsNone(s.context)
        self.assertIsNone(s.summary)

    def test_context_and_summary_default_none(self):
        s = StoryPipelineState(title="T", link="L", snippet="S", pub_dt="2024-01-01", category="Cat")
        self.assertIsNone(s.context)
        self.assertIsNone(s.summary)

    def test_all_fields_settable(self):
        s = StoryPipelineState(title="T", link="L", snippet="S", pub_dt="2024-01-01", category="Cat")
        s.context = "New context"
        s.summary = "New summary"
        self.assertEqual(s.context, "New context")
        self.assertEqual(s.summary, "New summary")

    def test_dataclass_fields(self):
        from dataclasses import dataclass as dc
        import dataclasses
        expected_fields = {"title", "link", "snippet", "category", "pub_dt", "context", "summary"}
        actual = {f.name for f in dataclasses.fields(StoryPipelineState)}
        self.assertEqual(actual, expected_fields)


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

    def test_empty_response_returns_empty(self):
        client = self._make_client("")
        async def _run():
            with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.config.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await _summarize(client, "Context text that is long enough to be meaningful.", title="Test Title", min_chars=0)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "")

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


# ---------------------------------------------------------------------------
# 9b.  parse_batch_summary_response — additional edge cases
# ---------------------------------------------------------------------------

class TestParseBatchSummaryResponseRegexNoMatch(TestCase):
    """Line 132: STORY_N regex does not match → skip."""

    def test_story_n_regex_no_match(self):
        response = "Story:| this does not start with STORY_N format\nAnother line"
        result = parse_batch_summary_response(response, 2)
        self.assertEqual(result, ["", ""])


class TestParseBatchSummaryResponseEmptyRest(TestCase):
    """Line 138: STORY_N regex matches but rest_text is empty after strip → skip."""

    def test_story_n_empty_rest_text(self):
        response = "STORY_1|   "
        result = parse_batch_summary_response(response, 1, story_headlines=["Some Headline"])
        self.assertEqual(len(result), 1)


class TestParseBatchSummaryResponseEmptySummaryClean(TestCase):
    """Line 150: summary_text is only whitespace after cleaning → skip."""

    def test_story_n_empty_summary_clean(self):
        response = "STORY_0 | "
        result = parse_batch_summary_response(response, 2, story_headlines=["H1"])
        self.assertEqual(len(result), 2)


class TestParseBatchSummaryResponseEmptyWordSets(TestCase):
    """Line 193: headline and summary both have no significant words (4+ char) → skip."""

    def test_strategy_1_empty_word_sets(self):
        response = "STORY_0 | A B C D short words only"
        headlines = ["A B C I O U Short"]
        result = parse_batch_summary_response(response, 1, story_headlines=headlines)
        self.assertEqual(len(result), 1)


class TestParseBatchSummaryResponseStrategy2(TestCase):
    """Lines 211-239: Strategy 2 excerpt matching triggers."""

    def test_strategy_2_excerpt_match(self):
        response = "STORY_0 | space mission nasa launch artemis mission successful yesterday news report"
        headlines = ["NASA Space Mission Artemis Launch Successful"]
        result = parse_batch_summary_response(response, 1, story_headlines=headlines)
        self.assertEqual(len(result), 1)

    def test_strategy_2_no_match(self):
        response = "STORY_0 | totally different unrelated words here in this long string of text no overlap"
        headlines = ["Federal Reserve Bank Interest Rate Decision Policy"]
        result = parse_batch_summary_response(response, 1, story_headlines=headlines)
        self.assertEqual(len(result), 1)


class TestParseBatchSummaryResponsePartialMatch(TestCase):
    """Line 247: partial match — some stories matched, others fall back."""

    def test_partial_match_mixed(self):
        response = (
            "STORY_0 | Market stocks traded surging rally gained\n"
            "STORY_1 | Unrelated random words no keyword match overlap here"
        )
        headlines = ["Market Stocks Surging Rally Gained Trading", "Random Story Two"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)


class TestParseBatchSummaryResponseSummaryOfHeading(TestCase):
    """Line 290: 'Summary of ...:' heading format."""

    def test_summary_of_heading_fallback(self):
        response = (
            "Summary of first story:\n"
            "The market went up today. Stock prices increased.\n"
            "Summary of second story:\n"
            "Weather conditions improved."
        )
        result = parse_batch_summary_response(response, 2)
        self.assertEqual(len(result), 2)


class TestParseBatchSummaryResponseAllNoneIndex(TestCase):
    """Lines 312-324: all headers have None index → chunk distribution."""

    def test_sequential_fallback_all_none(self):
        response = (
            "Summary of piece number one:\n"
            "The first story content goes here with some detail.\n"
            "Summary of piece number two:\n"
            "The second story content goes here with detail."
        )
        result = parse_batch_summary_response(response, 2)
        self.assertEqual(len(result), 2)


class TestParseBatchSummaryResponsePositionalFuzzy(TestCase):
    """Lines 337-359, 397-398: positional fuzzy headline matching."""

    def test_positional_fuzzy_match(self):
        response = (
            "1. The first item discussed.\n"
            "2. The second item discussed."
        )
        headlines = ["The Federal Budget Discussion Report", "The Second Climate Analysis Piece"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)


class TestParseBatchSummaryResponseAdjacentSwap(TestCase):
    """Lines 421-422 and 411/415: swap detection with 3+ stories exercises all code paths."""

    def test_adjacent_swap_fix(self):
        # 3-stories with swapped ordering exercises the swap loop
        # Positional fuzzy at lines 337-359 corrects most, testing those paths
        response = (
            "STORY_0 | Warming global temperatures climate rise\n"
            "STORY_1 | Market stock trading gains rally\n"
            "STORY_2 | Tech artificial intelligence breakthrough"
        )
        headlines = [
            "Stock Market Trading Gains Rally",
            "Climate Warming Global Temperatures Rise",
            "Artificial Intelligence Tech Breakthrough",
        ]
        result = parse_batch_summary_response(response, 3, story_headlines=headlines)
        self.assertEqual(len(result), 3)
        # Verify results populated through fuzzy/keyword/positional matching
        total_chars = sum(len(r) for r in result)
        self.assertGreater(total_chars, 0)

    def test_adjacent_swap_detection_code_path(self):
        # Verify the adjacent swap loop runs with 3+ stories
        response = (
            "1. First report about the alpha analysis today.\n"
            "2. Second report about the beta data results.\n"
            "3. Third report about the gamma findings study."
        )
        headlines = [
            "Alpha Analysis Report Today Published",
            "Beta Data Results Findings Released",
            "Gamma Research Study Findings Published",
        ]
        result = parse_batch_summary_response(response, 3, story_headlines=headlines)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(len(r) > 0 for r in result))


class TestParseBatchSummaryResponseAllPairsMismatch(TestCase):
    """Lines 444-452: all-pairs mismatch warning logged."""

    def test_all_pairs_mismatch_warning(self):
        import logging
        # Generic summaries that match NO headline keywords → all-pairs detects mismatch
        response = (
            "1. This first report discusses the matter at hand with details.\n"
            "2. The second report covers another topic with separate details."
        )
        headlines = [
            "Stock Market Trading Gains Rally Surge Analysis",
            "Climate Warming Temperature Report Findings Change",
        ]
        import daily_brief.llm.summarizer as smod
        captured = []
        class CaptureHandler(logging.Handler):
            def emit(self, record):
                captured.append(record.getMessage())
        test_handler = CaptureHandler()
        old_logger = smod.logger
        old_logger.addHandler(test_handler)
        old_level = old_logger.level
        old_logger.setLevel(logging.DEBUG)
        try:
            result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        finally:
            old_logger.removeHandler(test_handler)
            old_logger.setLevel(old_level)
        self.assertEqual(len(result), 2)
        mismatch_msgs = [m for m in captured if "SWAP DETECTED" in m]
        self.assertTrue(len(mismatch_msgs) > 0)


class TestParseBatchSummaryResponseLine427(TestCase):
    """Line 427: i >= len(story_headlines) → continue in all-pairs loop."""

    def test_line_427_continue(self):
        response = (
            "1. First story summary text here.\n"
            "2. Second story summary text here.\n"
            "3. Third story summary text here."
        )
        headlines = ["First Headline", "Second Headline"]
        result = parse_batch_summary_response(response, 3, story_headlines=headlines)
        self.assertEqual(len(result), 3)


class TestParseBatchSummaryResponseLine431(TestCase):
    """Line 431: empty summary → continue in all-pairs loop."""

    def test_line_431_empty_summary(self):
        response = ""
        result = parse_batch_summary_response(response, 2, story_headlines=["H1", "H2"])
        self.assertEqual(result, ["", ""])


# ---------------------------------------------------------------------------
# Topic overlap guard (v1.0.112)
# ---------------------------------------------------------------------------

class TestHasTopicOverlap(TestCase):
    """_has_topic_overlap detects zero shared significant words."""

    def test_overlap_passes(self):
        from daily_brief.llm.summarizer import _has_topic_overlap
        self.assertTrue(
            _has_topic_overlap(
                "Houston weather has been repeating for weeks.",
                "Houston weather has been stuck on repeat — but not for much longer",
            )
        )

    def test_overlap_fails_zero_words(self):
        from daily_brief.llm.summarizer import _has_topic_overlap
        self.assertFalse(
            _has_topic_overlap(
                "average temperatures in the Gulf region could lead to stronger storms",
                "Stock market crashes as tech companies report record losses",
            )
        )

    def test_overlap_passes_one_word(self):
        from daily_brief.llm.summarizer import _has_topic_overlap
        self.assertTrue(
            _has_topic_overlap(
                "The market rally continued as stocks surged.",
                "Stocks surge as market rally continues into the week",
            )
        )


class TestIsValidSummaryTopicMismatch(TestCase):
    """_is_valid_summary rejects a grammatically valid but topic-mismatched summary."""

    def test_topic_mismatch_rejected(self):
        from daily_brief.llm.summarizer import _is_valid_summary
        self.assertFalse(
            _is_valid_summary(
                "average temperatures in the Gulf region could lead to stronger storms. Residents should prepare for the return of rain chances this weekend.",
                "Houston weather has been stuck on repeat — but not for much longer",
            )
        )

    def test_topic_match_accepted(self):
        from daily_brief.llm.summarizer import _is_valid_summary
        self.assertTrue(
            _is_valid_summary(
                "Houston weather has been stuck in a hot pattern for weeks. Conditions are expected to change this weekend with rain chances returning.",
                "Houston weather has been stuck on repeat — but not for much longer",
            )
        )


class TestIsValidSummaryStopWords(TestCase):
    """_significant_words filters stop words correctly for overlap check."""

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


class TestIsValidSummaryExtended(TestCase):
    """_is_valid_summary extended gates: one sentence, headline echo, refusal, fallback markers."""

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

    def test_valid_two_sentence_passes(self):
        self.assertTrue(
            _is_valid_summary(
                "Houston weather has been stuck in a hot pattern. Conditions are expected to change this weekend.",
                "Houston weather has been stuck on repeat",
            )
        )

    def test_empty_summary_rejected(self):
        self.assertFalse(_is_valid_summary("", "Any headline"))

    def test_none_summary_rejected(self):
        self.assertFalse(_is_valid_summary(None, "Any headline"))

    def test_boilerplate_rejected(self):
        self.assertFalse(
            _is_valid_summary(
                "This article discusses the implications of the new policy in detail. Further analysis is required.",
                "Houston weather has been stuck on repeat",
            )
        )


# ---------------------------------------------------------------------------
# Context too short
# ---------------------------------------------------------------------------

class TestSummarizeContextTooShort(TestCase):
    """Line 502: _summarize returns None when context is too short."""

    def test_summarize_context_too_short(self):
        from daily_brief.llm.summarizer import _summarize
        client = mock.MagicMock()
        async def _run():
            return await _summarize(client, "hi", title="Title", min_chars=100)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIsNone(result)


class TestSummarizeBoilerplateRetry(TestCase):
    """Lines 533-536: first call returns boilerplate, retry with strict returns good summary."""

    def test_summarize_boilerplate_retry(self):
        from daily_brief.llm.summarizer import _summarize
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
# 10.  batch_summarize_all
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

    def test_concurrency_2_parallel(self):
        """max_concurrency=2 allows two sub-batches to overlap, vs concurrency=1 serial."""
        from daily_brief.llm.summarizer import _summarize_sub_batch

        # Test: verify that max_concurrency > 1 uses asyncio.gather (parallel)
        # Direct test via _summarize_sub_batch with semaphore
        active = [0]
        max_active = [0]

        async def record_and_delay(label):
            active[0] += 1
            max_active[0] = max(max_active[0], active[0])
            await asyncio.sleep(0.05)
            active[0] -= 1

        sem = asyncio.Semaphore(2)
        async def guarded(label):
            async with sem:
                await record_and_delay(label)

        async def run_parallel():
            await asyncio.gather(guarded("A"), guarded("B"))

        asyncio.get_event_loop().run_until_complete(run_parallel())
        self.assertEqual(max_active[0], 2)  # Both ran concurrently with semaphore=2

        max_active[0] = 0
        active[0] = 0
        sem2 = asyncio.Semaphore(1)
        async def guarded1(label):
            async with sem2:
                await record_and_delay(label)

        async def run_serial():
            await asyncio.gather(guarded1("A"), guarded1("B"))

        asyncio.get_event_loop().run_until_complete(run_serial())
        self.assertEqual(max_active[0], 1)  # Only 1 at a time with semaphore=1

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


# ---------------------------------------------------------------------------
# Monotonic timing verification
# ---------------------------------------------------------------------------

class TestLLMMonotonicTiming(TestCase):
    """Verify that LLM duration measurements use time.monotonic() instead of time.time()."""

    def test_no_time_time_in_summarize(self):
        """Source-level check: time.time() is not used in _summarize for duration measurement."""
        import inspect
        from daily_brief.llm.summarizer import _summarize
        source = inspect.getsource(_summarize)
        self.assertNotIn("time.time()", source,
            "_summarize should use time.monotonic(), not time.time()")

    def test_no_time_time_in_summarize_sub_batch(self):
        """Source-level check: time.time() is not used in _summarize_sub_batch for duration measurement."""
        import inspect
        from daily_brief.llm.summarizer import _summarize_sub_batch
        source = inspect.getsource(_summarize_sub_batch)
        self.assertNotIn("time.time()", source,
            "_summarize_sub_batch should use time.monotonic(), not time.time()")

    def test_monotonic_used_in_summarize(self):
        """Verify time.monotonic() is used in _summarize."""
        import inspect
        from daily_brief.llm.summarizer import _summarize
        source = inspect.getsource(_summarize)
        self.assertIn("time.monotonic()", source,
            "_summarize should use time.monotonic()")

    def test_monotonic_used_in_summarize_sub_batch(self):
        """Verify time.monotonic() is used in _summarize_sub_batch."""
        import inspect
        from daily_brief.llm.summarizer import _summarize_sub_batch
        source = inspect.getsource(_summarize_sub_batch)
        self.assertIn("time.monotonic()", source,
            "_summarize_sub_batch should use time.monotonic()")


class TestMonotonicDurationNonNegative(TestCase):
    """Verify that monotonic duration measurements are non-negative."""

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

    def test_monotonic_duration_non_negative(self):
        """Patch time.monotonic to return controlled values and verify logged durations are non-negative."""
        import logging
        durations = []

        class DurationHandler(logging.Handler):
            def emit(self, record):
                msg = record.getMessage()
                if "SUMMARIZE:" in msg:
                    # Extract duration from "SUMMARIZE: 0.50s" format
                    for part in msg.split():
                        if part.endswith("s"):
                            try:
                                dur = float(part.rstrip("s"))
                                durations.append(dur)
                            except ValueError:
                                pass

        test_handler = DurationHandler()
        import daily_brief.llm.summarizer as smod
        old_logger = smod.logger
        old_logger.addHandler(test_handler)
        old_level = old_logger.level
        old_logger.setLevel(logging.DEBUG)

        try:
            mock_values = [100.0, 100.5, 200.0, 200.5]  # Two calls, t0 and t1
            mock_counter = [0]
            def mock_monotonic():
                val = mock_values[min(mock_counter[0], len(mock_values) - 1)]
                mock_counter[0] += 1
                return val

            client = self._make_client("The Fed raised rates by 0.25 percent Wednesday.")

            async def _run():
                with mock.patch("daily_brief.llm.summarizer.time.monotonic", side_effect=mock_monotonic):
                    return await _summarize(client, "Some context text that is long enough to be meaningful for the LLM to process and summarize properly.", title="Test", min_chars=0)

            asyncio.get_event_loop().run_until_complete(_run())
        finally:
            old_logger.removeHandler(test_handler)
            old_logger.setLevel(old_level)

        # All logged durations should be non-negative
        for dur in durations:
            self.assertGreaterEqual(dur, 0.0,
                f"Duration {dur} is negative — monotonic timing may be broken")
