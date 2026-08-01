"""
Unit tests for src/daily_brief/llm/alerter.py.
"""
import asyncio
import os
import sys
from unittest import TestCase, mock
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from daily_brief.llm.alerter import (
    parse_alert_batch_response,
    batch_evaluate_alerts,
)


# ---------------------------------------------------------------------------
# 1.  parse_alert_batch_response
# ---------------------------------------------------------------------------

class TestParseAlertBatchResponseSTORY(TestCase):
    """STORY_N: TRUE/FALSE format parsing."""

    def test_story_zero_true(self):
        result = parse_alert_batch_response("STORY_0: TRUE")
        self.assertEqual(result, {0: True})

    def test_story_three_false(self):
        result = parse_alert_batch_response("STORY_3: FALSE")
        self.assertEqual(result, {3: False})

    def test_story_zero_false(self):
        result = parse_alert_batch_response("STORY_0: FALSE")
        self.assertEqual(result, {0: False})

    def test_multiple_story_lines(self):
        response = "STORY_0: TRUE\nSTORY_1: FALSE\nSTORY_2: TRUE"
        result = parse_alert_batch_response(response)
        self.assertEqual(result, {0: True, 1: False, 2: True})

    def test_story_with_whitespace(self):
        result = parse_alert_batch_response("  STORY_0: TRUE  ")
        self.assertEqual(result, {0: True})

    def test_story_lowercase_true(self):
        result = parse_alert_batch_response("STORY_0: true")
        self.assertEqual(result, {0: True})

    def test_story_lowercase_false(self):
        result = parse_alert_batch_response("STORY_0: false")
        self.assertEqual(result, {0: False})

    def test_story_mixed_case(self):
        response = "STORY_0: True\nSTORY_1: False"
        result = parse_alert_batch_response(response)
        self.assertEqual(result, {0: True, 1: False})

    def test_story_extra_text_before_colon(self):
        result = parse_alert_batch_response("STORY_0extra: TRUE")
        # int("0extra") raises ValueError, so this is skipped
        self.assertEqual(result, {})


class TestParseAlertBatchResponseNumbered(TestCase):
    """Numbered format (N: TRUE/FALSE) parsing."""

    def test_numbered_true(self):
        result = parse_alert_batch_response("0: TRUE")
        self.assertEqual(result, {0: True})

    def test_numbered_false(self):
        result = parse_alert_batch_response("1: FALSE")
        self.assertEqual(result, {1: False})

    def test_numbered_multiple(self):
        response = "0: TRUE\n1: FALSE\n2: TRUE\n3: FALSE"
        result = parse_alert_batch_response(response)
        self.assertEqual(result, {0: True, 1: False, 2: True, 3: False})

    def test_numbered_with_spaces(self):
        result = parse_alert_batch_response("  2 : TRUE  ")
        self.assertEqual(result, {2: True})

    def test_numbered_rejects_lowercase(self):
        result = parse_alert_batch_response("0: true")
        # The numbered fallback requires exact 'TRUE' or 'FALSE' (case-sensitive check on stripped value)
        self.assertEqual(result, {})


class TestParseAlertBatchResponseEdgeCases(TestCase):
    """Malformed lines, empty input, partial parse."""

    def test_empty_string(self):
        result = parse_alert_batch_response("")
        self.assertEqual(result, {})

    def test_none_split_error(self):
        # parse_alert_batch_response expects a string; None would fail at .split()
        # The function does not handle None, so we test empty string instead
        result = parse_alert_batch_response("")
        self.assertEqual(result, {})

    def test_whitespace_only_lines(self):
        result = parse_alert_batch_response("   \n  \n\t")
        self.assertEqual(result, {})

    def test_malformed_no_colon(self):
        result = parse_alert_batch_response("this line has no colon at all")
        self.assertEqual(result, {})

    def test_malformed_non_integer_index(self):
        result = parse_alert_batch_response("abc: TRUE")
        self.assertEqual(result, {})

    def test_malformed_story_non_int_suffix(self):
        result = parse_alert_batch_response("STORY_abc: TRUE")
        self.assertEqual(result, {})

    def test_garbage_text_ignored(self):
        response = "random garbage\nmore junk\nno format here"
        result = parse_alert_batch_response(response)
        self.assertEqual(result, {})

    def test_partial_parse_valid_and_invalid(self):
        response = "STORY_0: TRUE\nbad line\nSTORY_1: FALSE"
        result = parse_alert_batch_response(response)
        self.assertEqual(result, {0: True, 1: False})

    def test_story_no_value_after_colon(self):
        result = parse_alert_batch_response("STORY_0:")
        # idx_str="0", int("0")=0, val="" → "" == "TRUE" is False
        self.assertEqual(result, {0: False})

    def test_numbered_no_value_after_colon(self):
        result = parse_alert_batch_response("0:")
        # parts[1].strip() is "", not in ('TRUE', 'FALSE')
        self.assertEqual(result, {})

    def test_returns_int_keys_bool_values(self):
        response = "STORY_0: TRUE\nSTORY_1: FALSE"
        result = parse_alert_batch_response(response)
        self.assertEqual(set(result.keys()), {0, 1})
        self.assertTrue(all(isinstance(k, int) for k in result.keys()))
        self.assertTrue(all(isinstance(v, bool) for v in result.values()))

    def test_mixed_story_and_numbered(self):
        response = "STORY_0: TRUE\n1: FALSE"
        result = parse_alert_batch_response(response)
        self.assertEqual(result, {0: True, 1: False})


# ---------------------------------------------------------------------------
# 2.  batch_evaluate_alerts (mocked async client, Perf-8)
# ---------------------------------------------------------------------------

class TestBatchEvaluateAlerts(TestCase):
    """batch_evaluate_alerts with mocked async LLM client (Perf-8)."""

    class _Story:
        def __init__(self, title, summary, category, is_alert=None):
            self.title = title
            self.summary = summary
            self.category = category
            self.is_alert = is_alert if is_alert is not None else False
            self._alert_idx = None

    def _make_client(self, response_text):
        client = mock.MagicMock()
        msg = mock.MagicMock()
        msg.content = response_text
        choice = mock.MagicMock()
        choice.message = msg
        client.chat_completions_create = AsyncMock(return_value=mock.MagicMock(choices=[choice]))
        return client

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_empty_stories_returns_empty(self):
        result = self._run(batch_evaluate_alerts(mock.MagicMock(), []))
        self.assertEqual(result, {})

    def test_single_story_alert_true(self):
        stories = [self._Story("Title 1", "Valid summary text here.", "Tech")]
        client = self._make_client("STORY_0: TRUE")
        result = self._run(batch_evaluate_alerts(client, stories))
        self.assertEqual(result, {0: True})
        self.assertTrue(stories[0].is_alert)

    def test_single_story_alert_false(self):
        stories = [self._Story("Title 1", "Valid summary text here.", "Tech")]
        client = self._make_client("STORY_0: FALSE")
        result = self._run(batch_evaluate_alerts(client, stories))
        self.assertEqual(result, {0: False})
        self.assertFalse(stories[0].is_alert)

    def test_stories_unavailable_summary_excluded(self):
        stories = [
            self._Story("Title 1", "[Summary Unavailable]", "Tech"),
            self._Story("Title 2", "Valid summary text.", "Tech"),
        ]
        client = self._make_client("STORY_0: TRUE")
        result = self._run(batch_evaluate_alerts(client, stories))
        # Story 0 excluded, Story 1 gets index 0 → TRUE
        self.assertEqual(result[0], False)  # unavailable story stays False
        self.assertEqual(result[1], True)

    def test_stories_bracket_summary_excluded(self):
        stories = [
            self._Story("Title 1", "[Auto] Some auto text", "Tech"),
        ]
        client = self._make_client("")
        result = self._run(batch_evaluate_alerts(client, stories))
        # Bracket-starting summary excluded, no LLM call should be made for empty list
        self.assertEqual(result, {0: False})

    def test_multiple_categories_grouped(self):
        stories = [
            self._Story("Title 1", "Summary one.", "Tech"),
            self._Story("Title 2", "Summary two.", "News"),
        ]
        call_count = [0]
        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            msgs = kwargs.get("messages", args[1] if len(args) > 1 else [])
            user_content = msgs[1]["content"] if len(msgs) > 1 else ""
            # Each category indexes from 0 — return STORY_0 for each
            r = mock.MagicMock()
            r.choices = [mock.MagicMock(message=mock.MagicMock(content="STORY_0: TRUE"))]
            return r
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=side_effect)
        result = self._run(batch_evaluate_alerts(client, stories))
        self.assertEqual(call_count[0], 2)  # Two categories = two calls
        self.assertEqual(result[0], True)  # Tech story
        self.assertEqual(result[1], True)  # News story
        self.assertEqual(len(result), 2)

    def test_llm_exception_all_false(self):
        stories = [
            self._Story("Title 1", "Valid summary.", "Tech"),
            self._Story("Title 2", "Also valid summary.", "Tech"),
        ]
        client = mock.MagicMock()
        client.chat_completions_create = AsyncMock(side_effect=Exception("Connection refused"))
        async def _run():
            with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None):
                return await batch_evaluate_alerts(client, stories)
        result = self._run(_run())
        self.assertEqual(result, {0: False, 1: False})
        self.assertFalse(stories[0].is_alert)
        self.assertFalse(stories[1].is_alert)

    def test_stories_without_alert_idx_get_false(self):
        stories = [self._Story("Title 1", "Valid summary text.", "Tech")]
        client = self._make_client("STORY_5: TRUE")
        result = self._run(batch_evaluate_alerts(client, stories))
        # STORY_5 doesn't match _alert_idx=0, so story gets False
        self.assertEqual(result, {0: False})

    def test_returns_dict_mapping_global_index(self):
        stories = [
            self._Story("A", "Summary A.", "Tech"),
            self._Story("B", "Summary B.", "Tech"),
            self._Story("C", "Summary C.", "News"),
        ]
        client = self._make_client("STORY_0: TRUE\nSTORY_1: FALSE")
        result = self._run(batch_evaluate_alerts(client, stories))
        self.assertEqual(len(result), 3)
        self.assertEqual(set(result.keys()), {0, 1, 2})
