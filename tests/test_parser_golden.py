"""Golden-fixture + edge-case tests for parse_batch_summary_response() — compact."""

from __future__ import annotations

import importlib.util
import os
from unittest import TestCase

from daily_brief.llm.summarizer import parse_batch_summary_response

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
_fixture_spec = importlib.util.spec_from_file_location(
    "parser_golden_fixtures", os.path.join(FIXTURES_DIR, "parser_golden_fixtures.py")
)
_fixture_mod = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(_fixture_mod)
FIXTURES = _fixture_mod.FIXTURES


KEEP_IDS = {
    "canon_story_n_equals",
    "story_n_reordered_fuzzy",
    "numbered_simple",
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


def _run_test(self, fixture):
    result = parse_batch_summary_response(
        fixture["response"],
        fixture["count"],
        story_headlines=fixture.get("headlines"),
    )
    self.assertEqual(len(result), fixture["count"])
    self.assertEqual(len(result), len(fixture["expected"]))
    for i, (got, exp) in enumerate(zip(result, fixture["expected"])):
        self.assertEqual(got.strip(), exp.strip(), f"[{fixture['id']}] slot {i}")


for _f in CURATED:
    setattr(TestParserGoldenFixtures, f"test_golden__{_f['id']}", lambda s, f=_f: _run_test(s, f))
del _f


class TestParserEdgeCases(TestCase):
    def test_none_empty_zero(self):
        self.assertEqual(parse_batch_summary_response(None, 3), ["", "", ""])
        self.assertEqual(parse_batch_summary_response("", 3), ["", "", ""])
        self.assertEqual(parse_batch_summary_response("text", 0), [])

    def test_garbage_no_markers(self):
        result = parse_batch_summary_response("Totally random text\nNo structure.", 2)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(r.strip() == "" for r in result))

    def test_count_exceeds_entries(self):
        result = parse_batch_summary_response("1. First\n2. Second", 5)
        self.assertEqual(result[2].strip(), "")
        self.assertEqual(result[4].strip(), "")

    def test_pipe_in_content(self):
        result = parse_batch_summary_response("STORY_0 | h=summary with pipe A | B.", 1)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].strip())

    def test_numbered_variants(self):
        self.assertTrue(all(s.strip() for s in parse_batch_summary_response("1. First\n2. Second", 2)))
        self.assertTrue(all(s.strip() for s in parse_batch_summary_response("1) First\n2) Second", 2)))

    def test_keyword_match_tie_earliest_wins(self):
        """Equal headline scores return earliest index (strict >)."""
        from daily_brief.llm.summary_parser import _best_headline_keyword_match
        query = {"apple", "banana", "cherry"}
        headlines = ["Apple Banana Date", "Apple Cherry Date"]
        idx, score = _best_headline_keyword_match(
            query, headlines, min_length=4, denominator="headline"
        )
        self.assertEqual(idx, 0)
        self.assertAlmostEqual(score, 2 / 3)

    def test_all_pairs_mismatch_diagnostics(self):
        """All-pairs validation logs SWAP DETECTED but preserves output."""
        headlines = ["Morning News Update", "Weather Forecast", "Sports Recap"]
        response = (
            "STORY_0 = Weather is sunny and warm today.\n"
            "STORY_1 = Sports scores from the championship finals.\n"
            "STORY_2 = Breaking: local government announces new policy changes."
        )
        with self.assertLogs("daily_brief.llm.summary_parser", "WARNING") as cm:
            result = parse_batch_summary_response(response, 3, story_headlines=headlines)
        self.assertIn("Weather", result[1])
        self.assertIn("Sports", result[2])
        self.assertIn("SWAP DETECTED", "\n".join(cm.output))
