"""Batch summarizer — trimmed: success and partial failure."""
import asyncio
from unittest import TestCase, mock
from unittest.mock import AsyncMock
from daily_brief.llm.summarizer import StoryPipelineState, batch_summarize_all

def _make_story(title, category, context=None, snippet=""):
    s = StoryPipelineState(title, "http://x", snippet, "2024-01-01", category)
    s.context = context
    s.summary = None
    return s

def _make_success_client(headline_map):
    async def side(**kwargs):
        r = mock.MagicMock()
        lines = [f"STORY_{i} | {hl}={headline_map[hl]}" for i, hl in enumerate(sorted(headline_map.keys()))]
        r.choices = [mock.MagicMock(message=mock.MagicMock(content="\n".join(lines)))]
        return r
    c = mock.MagicMock()
    c.chat_completions_create = AsyncMock(side_effect=side)
    return c

class TestBatchSummarizeAll(TestCase):
    def test_batch_summary_parsing_success(self):
        stories = [
            _make_story("Market Rally Continues", "Finance"),
            _make_story("Climate Report Warming", "Climate"),
        ]
        headlines = {
            "Market Rally Continues": "Market rally continued. Stocks surged. Prices climbed.",
            "Climate Report Warming": "Climate report shows warming. Scientists confirm trend.",
        }
        client = _make_success_client(headlines)
        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        return await batch_summarize_all(client, stories, batch_size=2)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result.total_stories, 2)
        self.assertIn("Market rally", stories[0].summary)
        self.assertIn("Climate report", stories[1].summary)

class TestBatchPartialFailure(TestCase):
    def test_batch_partial_failure(self):
        stories = [
            _make_story("Tech A", "Tech"), _make_story("Tech B", "Tech"),
            _make_story("News A", "News"), _make_story("News B", "News"),
        ]
        async def side(**kwargs):
            r = mock.MagicMock()
            msg = kwargs["messages"][1]["content"]
            if "Tech" in msg:
                raise RuntimeError("Tech batch failed")
            r.choices = [mock.MagicMock(message=mock.MagicMock(
                content="STORY_0 | News A=News summary A. Detail here.\nSTORY_1 | News B=News summary B. Detail here."
            ))]
            return r
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side)
        async def _run():
            with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_ATTEMPTS", 1):
                with mock.patch("daily_brief.llm.summarizer.LLM_SUMMARY_RETRY_BACKOFF", []):
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                        with mock.patch("daily_brief.llm.summarizer._summarize", new_callable=AsyncMock, return_value=None):
                            return await batch_summarize_all(client, stories, batch_size=2)
        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertTrue(not stories[0].summary or stories[0].summary.startswith("[Auto]"))
        self.assertIn("News summary", stories[2].summary)

if __name__ == "__main__":
    import unittest
    unittest.main()
