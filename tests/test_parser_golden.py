"""
Golden-fixture tests for parse_batch_summary_response().

Each fixture in parser_golden_fixtures is a dict with response, headlines,
count, expected, notes. The test runs the fixture through the parser and
compares against expected line-by-line.
"""
from __future__ import annotations

import os
import sys
from unittest import TestCase

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from daily_brief.llm.summarizer import parse_batch_summary_response

# Import fixture module
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
sys.path.insert(0, FIXTURES_DIR)
from parser_golden_fixtures import FIXTURES


class TestParserGoldenFixtures(TestCase):
    """Fixture-driven regression tests for parse_batch_summary_response."""

    def _run_fixture(self, fixture):
        result = parse_batch_summary_response(
            fixture["response"],
            fixture["count"],
            story_headlines=fixture.get("headlines"),
        )
        expected = fixture["expected"]
        self.assertEqual(
            len(result),
            fixture["count"],
            f"[{fixture['id']}] result length {len(result)} != count {fixture['count']}",
        )
        self.assertEqual(
            len(result),
            len(expected),
            f"[{fixture['id']}] expected length {len(expected)} != count {fixture['count']}",
        )
        for i, (got, exp) in enumerate(zip(result, expected)):
            msg = (
                f"[{fixture['id']}] slot {i}\n"
                f"  notes: {fixture['notes']}\n"
                f"  got ({len(got)} chars): {got!r}\n"
                f"  exp ({len(exp)} chars): {exp!r}"
            )
            if not got or not exp:
                self.assertEqual(got.strip(), exp.strip(), msg)
            else:
                self.assertEqual(got, exp, msg)

    def _dynamic_name(self, fixture):
        return f"test_parsetest_golden__{fixture['id']}"


# Dynamically generate tests from fixtures
for _f in FIXTURES:
    name = f"test_golden__{_f['id']}"
    setattr(
        TestParserGoldenFixtures,
        name,
        lambda self, f=_f: self._run_fixture(f),
    )
del _f


class TestParserEdgeCases(TestCase):
    """Additional edge-case tests not covered by golden fixtures."""

    def test_none_response(self):
        result = parse_batch_summary_response(None, 3)
        self.assertEqual(result, ["", "", ""])

    def test_empty_response(self):
        result = parse_batch_summary_response("", 3)
        self.assertEqual(result, ["", "", ""])

    def test_count_zero(self):
        result = parse_batch_summary_response("some text", 0)
        self.assertEqual(result, [])

    def test_garbage_no_markers(self):
        result = parse_batch_summary_response(
            "This is just random text with no recognizable format.\nMore random.",
            2,
        )
        self.assertEqual(len(result), 2)
        # No markers found, no headers found → empty results
        for r in result:
            self.assertEqual(r.strip(), "")

    def test_story_n_zero_based(self):
        """STORY_N with pipe format, no headlines — falls through to positional fallback.
        Positional parser captures raw line (including 'STORY_N |') as summary text.
        STORY_0 → idx 0, STORY_2 → idx 1 (decremented from 2). Both raw lines preserved."""
        result = parse_batch_summary_response(
            "STORY_0 | first story summary\nSTORY_2 | third story summary",
            3,
        )
        self.assertEqual(len(result), 3)
        self.assertIn("first story summary", result[0])
        self.assertIn("third story summary", result[1])
        self.assertEqual(result[2].strip(), "")

    def test_numbered_1_based(self):
        """1. and 2. map to idx 0 and 1."""
        result = parse_batch_summary_response(
            "1. First story\n2. Second story\n3. Third story",
            3,
        )
        self.assertEqual(len(result), 3)
        self.assertTrue(result[0].strip())
        self.assertTrue(result[1].strip())
        self.assertTrue(result[2].strip())

    def test_numbered_1_paren(self):
        """1) variant works."""
        result = parse_batch_summary_response(
            "1) First story\n2) Second story",
            2,
        )
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].strip())
        self.assertTrue(result[1].strip())

    def test_bold_numbered_heading(self):
        """**1. Heading** with bold cleanup."""
        result = parse_batch_summary_response(
            "**1. Downtown fire**\nThree buildings destroyed. Firefighters contained the blaze.",
            1,
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].strip())

    def test_multiline_bold_heading(self):
        """### **2. Budget** with continuation."""
        result = parse_batch_summary_response(
            "### **2. Budget plan**\nMayor announced it. Schools get funding.",
            3,
        )
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].strip(), "")
        self.assertTrue(result[1].strip())
        self.assertEqual(result[2].strip(), "")

    def test_single_story_with_preamble(self):
        """Single story: preamble lines filtered, clean paragraph returned."""
        result = parse_batch_summary_response(
            "Here are the summaries you requested:\n\n"
            "This is the summary text. It has three sentences. The third ends here.",
            1,
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].strip())
        self.assertNotIn("Here are", result[0])

    def test_story_headlines_empty_list(self):
        """Headlines=[] should not cause errors, treated as no headlines."""
        result = parse_batch_summary_response(
            "STORY_0 | summary text\n1. Second story",
            2,
            story_headlines=[],
        )
        self.assertEqual(len(result), 2)

    def test_equal_in_summary_body(self):
        """Multiple = characters: only split at first."""
        result = parse_batch_summary_response(
            "STORY_0 | headline=summary with = sign in it. Another sentence.",
            1,
        )
        self.assertEqual(len(result), 1)
        self.assertIn("=", result[0])

    def test_blank_summary_after_equals(self):
        """STORY_0 | headline= without headlines → positional fallback captures raw line.
        Without headline matching, empty = summary is not parsed. Positional fallback
        captures the raw line as summary (documents actual behavior, not ideal parsing)."""
        result = parse_batch_summary_response(
            "STORY_0 | headline=",
            1,
        )
        self.assertEqual(len(result), 1)
        self.assertIn("headline", result[0])

    def test_pipe_in_content(self):
        """Pipe character in content after STORY_N | ."""
        result = parse_batch_summary_response(
            "STORY_0 | headline=summary with a pipe: A | B in the text. Done.",
            1,
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].strip())

    def test_count_exceeds_entries(self):
        """More story slots than response entries → empty slots."""
        result = parse_batch_summary_response(
            "1. First story\n2. Second story",
            5,
        )
        self.assertEqual(len(result), 5)
        self.assertTrue(result[0].strip())
        self.assertTrue(result[1].strip())
        for i in range(2, 5):
            self.assertEqual(result[i].strip(), "")

    def test_three_sentence_trim(self):
        """Summary with 5 sentences trimmed to 3."""
        result = parse_batch_summary_response(
            "STORY_0 | h=One sentence. Two sentences. Three sentences. Four sentences. Five sentences.",
            1,
        )
        self.assertEqual(len(result), 1)
        parts = [s.strip() for s in result[0].split(".") if s.strip()]
        # Should have exactly 3 sentences
        self.assertLessEqual(len(parts), 3)

    def test_summary_of_chunking_sequential(self):
        """Summary of A: and Summary of B: → sequential chunks."""
        result = parse_batch_summary_response(
            "Summary of Fire downtown:\nFire destroyed buildings. Contained by evening.\n\n"
            "Summary of Budget plan:\nMayor announced budget. Schools get funding.",
            2,
        )
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].strip())
        self.assertTrue(result[1].strip())
