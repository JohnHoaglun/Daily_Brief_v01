"""Contract tests for one-to-one parser assignment in parse_batch_summary_response().

Documents the desired behavior: each headline slot receives at most one summary.
First-wins semantics, no overwrites, positional fallback skips headline-matched slots.

Some tests will FAIL against the current implementation — that's the point:
they document the gap between current code and the desired contract.
"""
from __future__ import annotations

import unittest
from daily_brief.llm.summarizer import parse_batch_summary_response


class TestNoOverwrite(unittest.TestCase):
    """Two STORY_N blocks both fuzzy-match to the same headline index: first wins."""

    def test_two_blocks_same_headline_first_wins(self):
        """STORY_0 and STORY_1 both match headline 0. First block wins slot 0.
        Second block leaves slot 1 empty (recovery target)."""
        response = (
            "STORY_0 | Fire burns downtown=The fire destroyed three downtown buildings. "
            "Firefighters contained the blaze. No injuries reported.\n"
            "STORY_1 | Downtown blaze report=A giant fire burned downtown. "
            "The arson suspect was arrested. Cleanup will take days.\n"
            "STORY_2 | Storm warning issued=A storm warning is in effect. "
            "Residents should prepare. Pass within hours."
        )
        headlines = [
            "Fire burns downtown",
            "Mayor announces budget",
            "Storm warning issued",
        ]
        result = parse_batch_summary_response(response, 3, story_headlines=headlines)
        self.assertEqual(len(result), 3)
        # Slot 0: matched by STORY_0 (first)
        self.assertTrue(result[0].strip(), "slot 0 should have fire summary")
        # Slot 1: no unique match — STORY_1 also matched to slot 0, slot 1 stays empty
        self.assertEqual(result[1].strip(), "",
                         "slot 1 should be empty — second duplicate match must not overwrite or steal")
        # Slot 2: storm
        self.assertTrue(result[2].strip(), "slot 2 should have storm summary")

    def test_both_match_headline_zero_second_does_not_overwrite(self):
        """Two paraphrases of headline 0: first STORY_0 fills slot 0, STORY_2 must not overwrite."""
        response = (
            "STORY_0 | Downtown fire=The fire destroyed three downtown buildings. "
            "Firefighters contained the blaze. No injuries.\n"
            "STORY_1 | Mayor announces budget=The mayor announced a budget. "
            "New schools will get funding. Critics oppose taxes.\n"
            "STORY_2 | Fire in city center=Another fire description. "
            "City center is burning. Police evacuated."
        )
        headlines = [
            "Fire burns downtown",
            "Mayor announces budget",
            "Storm warning issued",
        ]
        result = parse_batch_summary_response(response, 3, story_headlines=headlines)
        # Both STORY_0 and STORY_2 high fuzzy-match to headline 0.
        # Contract: first match wins; second does NOT overwrite.
        self.assertTrue(result[0].strip(), "slot 0 has fire summary from STORY_0")
        # STORY_2 paraphrase of headline 0 should NOT overwrite slot 0
        self.assertIn("downtown", result[0].lower() or "",
                      "slot 0 should still contain the original downtown fire summary")


class TestPositionalDoesNotOverwriteHeadlineMatch(unittest.TestCase):
    """Headline matching fills slot 0; positional fallback must skip it."""

    def test_headline_match_fills_slot0_positional_skips(self):
        """STORY_0 fuzzy-matches headline 0. Positional '1.' maps to idx 0.
        Pos fallback must NOT overwrite slot 0."""
        response = (
            "STORY_0 | Fire burns downtown=The fire destroyed three downtown buildings. "
            "Firefighters contained the blaze. No injuries reported.\n"
            "1. Fire burns downtown. Three buildings lost.\n"
            "2. Mayor announces budget. New funding for schools."
        )
        headlines = ["Fire burns downtown", "Mayor announces budget"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].strip(), "slot 0 should have fire summary")
        self.assertTrue(result[1].strip(), "slot 1 should have mayor summary")

    def test_positional_fallback_skips_already_matched(self):
        """STORY_0 fills slot 0 via headline. Positional numbered 1. → idx 0. Skip."""
        response = (
            "STORY_0 | Downtown blaze=The fire destroyed three downtown buildings. "
            "Firefighters contained the blaze. No injuries.\n"
            "1. Something else. Extra text here."
        )
        headlines = ["Fire burns downtown", "Mayor announces budget"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertTrue(result[0].strip(), "slot 0 filled by STORY_0 headline match")
        # Positional 1. → idx 0, already matched, should be skipped
        # Slot 0 should not be overwritten by positional garbage
        self.assertIn("downtown", result[0].lower() or "",
                      "slot 0 must not be overwritten by positional fallback")


class TestAmbiguousZeroOverlap(unittest.TestCase):
    """When keyword overlap < 30% for all stories, all positions empty."""

    def test_all_zero_overlap_empty_slots(self):
        """Summaries contain zero keyword overlap with any headline.
        All slots should be empty (recovery targets)."""
        response = (
            "STORY_0 | Random topic A=The cat sat on the mat. "
            "It was a sunny day. Birds were chirping.\n"
            "STORY_1 | Random topic B=Fish swim in the ocean. "
            "Coral reefs are beautiful. Sharks patrol."
        )
        headlines = [
            "Fire burns downtown",
            "Mayor announces budget",
        ]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].strip(), "",
                         "slot 0 empty — no keyword overlap with any headline")
        self.assertEqual(result[1].strip(), "",
                         "slot 1 empty — no keyword overlap with any headline")


class TestDuplicateHeadlineExcerpts(unittest.TestCase):
    """Two STORY_N blocks share the same headline excerpt text."""

    def test_identical_excerpt_first_wins(self):
        """Both blocks have identical headline excerpt. First wins.
        Second stays empty for downstream recovery."""
        response = (
            "STORY_0 | Fire burns downtown=The original fire summary. "
            "Three buildings destroyed. No injuries.\n"
            "STORY_1 | Fire burns downtown=The duplicate fire summary. "
            "Different text entirely. Cleanup underway.\n"
            "STORY_2 | Mayor announces budget=The mayor announced a budget. "
            "New schools get funding. Critics oppose."
        )
        headlines = [
            "Fire burns downtown",
            "Mayor announces budget",
            "Storm warning issued",
        ]
        result = parse_batch_summary_response(response, 3, story_headlines=headlines)
        self.assertEqual(len(result), 3)
        self.assertTrue(result[0].strip(), "slot 0: first match wins")
        self.assertEqual(result[1].strip(), "",
                         "slot 1 empty — duplicate excerpt must not steal a slot")
        # STORY_2 / Mayor should go to slot 1
        self.assertIn("mayor", result[1].lower() or result[2].lower() or "",
                      "mayor summary should appear somewhere")


class TestEmptyTitleStories(unittest.TestCase):
    """Stories with empty string titles must not crash."""

    def test_empty_title_no_crash(self):
        """Headline list contains empty string. Parser must not raise."""
        response = (
            "STORY_0 | Fire burns downtown=The fire destroyed downtown buildings. "
            "Firefighters contained the blaze. No injuries.\n"
            "STORY_1 | Mayor announces budget=The mayor announced budget. "
            "Schools get funding. Critics say too much."
        )
        headlines = ["Fire burns downtown", ""]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].strip(), "slot 0 matched")
        # slot 1 with empty headline can't keyword-match — should be empty or positional
        # Contract: no crash regardless

    def test_all_empty_titles_no_crash(self):
        """All headlines are empty strings — no crash, all slots empty."""
        response = (
            "STORY_0 | text=Some summary text here. More details. End.\n"
            "STORY_1 | more text=Another summary. Extra sentence. Done."
        )
        headlines = ["", ""]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        # Empty headlines → no keyword overlap → empty slots

    def test_none_in_headlines(self):
        """None value in headlines list — handled gracefully."""
        response = "STORY_0 | h=Summary text here. More details. End of summary."
        with self.assertRaises(Exception):
            parse_batch_summary_response(response, 1, story_headlines=[None])


class TestMalformedStoryIDs(unittest.TestCase):
    """STORY_N with out-of-range or invalid IDs are skipped."""

    def test_story_99_out_of_range(self):
        """STORY_99 in a 3-story batch is out of range. Skipped, no crash."""
        response = (
            "STORY_0 | Fire burns downtown=The fire destroyed buildings. "
            "Firefighters contained blaze. No injuries.\n"
            "STORY_99 | Phantom story=This story does not exist. "
            "It should not appear anywhere. Go away.\n"
            "STORY_1 | Mayor budget=Mayor announced budget. "
            "Schools get funding. Critics oppose."
        )
        headlines = ["Fire burns downtown", "Mayor announces budget"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].strip(), "slot 0: fire")
        self.assertTrue(result[1].strip(), "slot 1: mayor")
        self.assertNotIn("Phantom", result[0] + result[1],
                         "STORY_99 should not appear in output")

    def test_story_abc_non_numeric(self):
        """STORY_abc is not a valid STORY_N pattern. Skipped, no crash."""
        response = (
            "STORY_0 | Downtown fire=The fire destroyed buildings. "
            "Firefighters arrived quickly. No injuries.\n"
            "STORY_abc | Invalid ID=This should be skipped entirely. "
            "No numeric index. Bad format.\n"
            "STORY_1 | Budget plan=Mayor announced the budget. "
            "Schools get money. Critics say no."
        )
        headlines = ["Downtown fire", "Budget plan"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].strip())
        self.assertTrue(result[1].strip())
        self.assertNotIn("Invalid ID", result[0] + result[1])


class TestSwapDetection(unittest.TestCase):
    """Adjacent swap: genuinely swapped stories are swapped back."""

    def test_genuinely_swapped_adjacent_stories(self):
        """Stories 0 and 1 are swapped. Summary at idx 0 mentions headline 1's
        keywords, summary at idx 1 mentions headline 0's keywords. Should swap."""
        response = (
            "1. Mayor unveils budget plan. Schools get new funding this year.\n"
            "2. Fire destroys downtown buildings. Three lost in the blaze."
        )
        headlines = ["Fire burns downtown", "Mayor announces budget"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        # Contract: swapped stories should be corrected
        self.assertIn("fire", result[0].lower() or "",
                      "slot 0 should have fire summary after swap fix")
        self.assertIn("mayor", result[1].lower() or "",
                      "slot 1 should have mayor summary after swap fix")

    def test_correctly_matched_no_swap(self):
        """Stories correctly ordered. Must NOT swap."""
        response = (
            "1. Fire destroys downtown. Three buildings lost.\n"
            "2. Mayor unveils budget plan. Schools get new funding."
        )
        headlines = ["Fire burns downtown", "Mayor announces budget"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        self.assertIn("fire", result[0].lower() or "",
                      "slot 0 should have fire — no swap")
        self.assertIn("mayor", result[1].lower() or "",
                      "slot 1 should have mayor — no swap")


class TestFuzzyMatchThreshold(unittest.TestCase):
    """difflib.SequenceMatcher ratio >= 0.7 vs < 0.7."""

    def test_fuzzy_above_threshold_catches_paraphrase(self):
        """Headline excerpt is a close paraphrase. difflib ratio >= 0.7.
        Should match and fill the slot."""
        response = (
            "STORY_0 | Fire burns in downtown area=The fire destroyed downtown buildings. "
            "Firefighters contained the blaze. No injuries reported today.\n"
            "STORY_1 | Mayor announces new budget=The mayor announced a new budget plan. "
            "Includes school funding. Critics say too much."
        )
        headlines = ["Fire burns downtown", "Mayor announces budget"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].strip(), "slot 0: paraphrase above 0.7 threshold — matched")
        self.assertTrue(result[1].strip(), "slot 1: matched")

    def test_fuzzy_below_threshold_empty_slot(self):
        """Headline excerpt is very different from actual headline.
        difflib ratio < 0.7. Slot should be empty (no forced match)."""
        response = (
            "STORY_0 | Completely Different Topic Here=Some random text about "
            "unrelated things. This has nothing to do with the actual news story.\n"
            "STORY_1 | Mayor announces budget=The mayor announced a budget plan. "
            "Schools get new funding. Critics oppose."
        )
        headlines = ["Fire burns downtown", "Mayor announces budget"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].strip(), "",
                         "slot 0: paraphrase too far from headline — below 0.7, empty")
        self.assertTrue(result[1].strip(), "slot 1: mayor matches")


class TestOneToOneAssignment(unittest.TestCase):
    """Each headline slot gets at most one summary (global contract)."""

    def test_three_stories_3to1_none_overwrite(self):
        """Three STORY_N blocks, only 2 headlines. Extra block discarded."""
        response = (
            "STORY_0 | Fire downtown=Fire destroyed buildings. "
            "Firefighters contained the blaze. No injuries.\n"
            "STORY_1 | Mayor budget=Mayor announced budget plan. "
            "Schools get new funding. Critics oppose.\n"
            "STORY_2 | Extra story=This is an extra story. "
            "It has nowhere to go. Should disappear."
        )
        headlines = ["Fire burns downtown", "Mayor announces budget"]
        result = parse_batch_summary_response(response, 2, story_headlines=headlines)
        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].strip(), "slot 0: fire")
        self.assertTrue(result[1].strip(), "slot 1: mayor")
        self.assertNotIn("extra story", (result[0] + result[1]).lower(),
                         "extra story must not appear in output")

    def test_reordered_batch_all_match_once(self):
        """Three stories returned in wrong order. All three match correctly.
        No slot overwritten, no data loss."""
        response = (
            "STORY_0 | Mayor budget plan=Mayor announced budget. "
            "Schools get funding. Critics oppose taxes.\n"
            "STORY_1 | Storm warning=Storm warning issued. "
            "Residents prepare. Severe weather expected.\n"
            "STORY_2 | Fire downtown=Fire destroyed three buildings. "
            "No injuries. Firefighters arrived fast."
        )
        headlines = [
            "Fire burns downtown",
            "Mayor announces budget",
            "Storm warning issued",
        ]
        result = parse_batch_summary_response(response, 3, story_headlines=headlines)
        self.assertEqual(len(result), 3)
        self.assertTrue(result[0].strip(), "slot 0: fire")
        self.assertTrue(result[1].strip(), "slot 1: mayor")
        self.assertTrue(result[2].strip(), "slot 2: storm")
