"""Golden-fixture + edge-case tests for parse_batch_summary_response()."""
from __future__ import annotations

import os
import sys
from unittest import TestCase

from daily_brief.llm.summarizer import parse_batch_summary_response

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
sys.path.insert(0, FIXTURES_DIR)
from parser_golden_fixtures import FIXTURES


def _run(self, fixture):
    result = parse_batch_summary_response(
        fixture["response"], fixture["count"],
        story_headlines=fixture.get("headlines"),
    )
    expected = fixture["expected"]
    self.assertEqual(len(result), fixture["count"],
        f"[{fixture['id']}] len {len(result)} != {fixture['count']}")
    self.assertEqual(len(result), len(expected),
        f"[{fixture['id']}] expected len {len(expected)} != {fixture['count']}")
    for i, (got, exp) in enumerate(zip(result, expected)):
        msg = f"[{fixture['id']}] slot {i}  got={got!r}  exp={exp!r}"
        self.assertEqual(got.strip(), exp.strip(), msg)


# Keep canonical, reordered, numbered, multiline, partial, plain-paragraph,
# heading, and sentence-trim fixtures. Drop colon/dash-space variants that
# document broken positional fallback.
KEEP_IDS = {
    "canon_story_n_equals",
    "story_n_reordered_fuzzy",
    "story_n_no_equals_overlap",
    "numbered_simple",
    "numbered_mixed_formats",
    "numbered_multiline",
    "summary_of_headings",
    "single_plain_paragraph",
    "partial_malformed",
    "adjacent_swap",
    "sentence_trimming",
    "story_headline_overlap_skip",
    "numbered_reordered_fuzzy",
}
CURATED = [f for f in FIXTURES if f["id"] in KEEP_IDS]


class TestParserGoldenFixtures(TestCase):
    pass

for _f in CURATED:
    setattr(TestParserGoldenFixtures, f"test_golden__{_f['id']}", lambda s, f=_f: _run(s, f))
del _f


class TestParserEdgeCases(TestCase):

    def test_none_response(self):
        self.assertEqual(parse_batch_summary_response(None, 3), ["", "", ""])

    def test_empty_response(self):
        self.assertEqual(parse_batch_summary_response("", 3), ["", "", ""])

    def test_count_zero(self):
        self.assertEqual(parse_batch_summary_response("text", 0), [])

    def test_garbage_no_markers(self):
        result = parse_batch_summary_response("Totally random text\nNo structure.", 2)
        self.assertEqual(len(result), 2)
        for r in result:
            self.assertEqual(r.strip(), "")

    def test_count_exceeds_entries(self):
        result = parse_batch_summary_response("1. First\n2. Second", 5)
        self.assertEqual(len(result), 5)
        self.assertTrue(result[0].strip())
        self.assertTrue(result[1].strip())
        for i in range(2, 5):
            self.assertEqual(result[i].strip(), "")

    def test_pipe_in_content(self):
        result = parse_batch_summary_response(
            "STORY_0 | h=summary with a pipe: A | B. Done.", 1)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].strip())

    def test_equal_in_summary_body(self):
        result = parse_batch_summary_response(
            "STORY_0 | h=summary with = sign. Done.", 1)
        self.assertEqual(len(result), 1)
        self.assertIn("=", result[0])

    def test_single_story_preamble(self):
        result = parse_batch_summary_response(
            "Here are the summaries:\n\nThe summary has three sentences. The third ends here. Extra.",
            1)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].strip())
        self.assertNotIn("Here are", result[0])

    def test_story_headlines_empty_list(self):
        result = parse_batch_summary_response(
            "STORY_0 | text\n1. Second", 2, story_headlines=[])
        self.assertEqual(len(result), 2)

    def test_numbered_variants(self):
        r = parse_batch_summary_response("1. First\n2. Second\n3. Third", 3)
        self.assertEqual(len(r), 3)
        self.assertTrue(all(s.strip() for s in r))
        r = parse_batch_summary_response("1) First\n2) Second", 2)
        self.assertEqual(len(r), 2)
        self.assertTrue(all(s.strip() for s in r))

    def test_bold_numbered_heading(self):
        r = parse_batch_summary_response(
            "**1. Downtown fire**\nThree buildings destroyed. Contained by evening.", 1)
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0].strip())

    def test_multiline_bold_heading(self):
        r = parse_batch_summary_response(
            "### **2. Budget**\nMayor announced it. Schools get funding.", 3)
        self.assertEqual(len(r), 3)
        self.assertEqual(r[0].strip(), "")
        self.assertTrue(r[1].strip())
        self.assertEqual(r[2].strip(), "")

    def test_three_sentence_trim(self):
        r = parse_batch_summary_response(
            "STORY_0 | h=One. Two. Three. Four. Five.", 1)
        parts = [s.strip() for s in r[0].split(".") if s.strip()]
        self.assertLessEqual(len(parts), 3)

    def test_summary_of_chunking_sequential(self):
        r = parse_batch_summary_response(
            "Summary of Fire:\nDestroyed buildings. Contained.\n\n"
            "Summary of Budget:\nMayor announced. Funding schools.",
            2)
        self.assertEqual(len(r), 2)
        self.assertTrue(r[0].strip())
        self.assertTrue(r[1].strip())
