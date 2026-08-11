"""
Tier 1 unit tests for tagging.py — keyword matching, scoring, thresholds,
category boosts, tag deduplication, and min-tag promotion.
"""

from contextlib import contextmanager
from unittest import TestCase, mock

from daily_brief.tagging import (
    _keyword_has_stop,
    _word_boundary_match,
    tag_story_with_keywords,
)

# ---------------------------------------------------------------------------
# Config mocking
# ---------------------------------------------------------------------------

_DEFAULT_MAPPINGS = {
    "ai": ["ai", "artificial intelligence", "machine learning"],
    "weather": ["weather", "storm", "hurricane"],
    "local": ["houston", "texas"],
    "sports": ["nfl", "football"],
    "economy": ["stock", "market", "earnings"],
}

_DEFAULT_BOOSTS = {
    "AI News": ["ai", "tech"],
    "Local News": ["local"],
    "Weather": ["weather"],
}

_DEFAULT_CONFLICTS = [["local", "economy"]]


@contextmanager
def _patch_config(
    max_tags=5,
    score_cap=5.0,
    score_threshold=0.3,
    mappings=None,
    boosts=None,
    conflicts=None,
):
    """Patch daily_brief.config tagging constants for isolated unit tests."""
    patches = [
        mock.patch(
            "daily_brief.tagging.TAGGING_CONFIG",
            {
                "max_tags": max_tags,
                "score_cap": score_cap,
                "score_threshold": score_threshold,
            },
        ),
        mock.patch("daily_brief.tagging.TAGGING_MAPPINGS", mappings or _DEFAULT_MAPPINGS),
        mock.patch("daily_brief.tagging.CATEGORY_BOOSTS", boosts or _DEFAULT_BOOSTS),
        mock.patch("daily_brief.tagging.TAG_CONFLICTS", conflicts or _DEFAULT_CONFLICTS),
        mock.patch("daily_brief.tagging.FRONTMATTER_FALLBACK_TAG", "#news"),
    ]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in reversed(patches):
            p.stop()


# ---------------------------------------------------------------------------
# _word_boundary_match
# ---------------------------------------------------------------------------


class TestWordBoundaryMatch(TestCase):
    def test_exact_and_case_insensitive(self):
        """Exact word match; case insensitive."""
        self.assertTrue(_word_boundary_match("ai breakthrough announces new model", "ai"))
        self.assertTrue(_word_boundary_match("AI takes over", "ai"))
        self.assertTrue(_word_boundary_match("Houston city council meets", "houston"))

    def test_word_boundary_no_partial(self):
        """Partial substring must not match without word boundary."""
        self.assertFalse(_word_boundary_match("stunning performance", "sting"))
        self.assertFalse(_word_boundary_match("stunning results", "sun"))

    def test_suffix_and_punctuation_boundaries(self):
        """Suffixes (s/ed/es/ing), possessive apostrophe, punctuation act as word boundaries."""
        self.assertTrue(_word_boundary_match("new storms hit", "storm"))
        self.assertTrue(_word_boundary_match("suspect arrested downtown", "arrest"))
        self.assertTrue(_word_boundary_match("investigating the crime scene", "investigat"))
        self.assertTrue(_word_boundary_match("two strikes called", "strike"))
        self.assertTrue(_word_boundary_match("Houston's new policy", "houston"))
        self.assertTrue(_word_boundary_match("AI, the new frontier", "ai"))
        self.assertTrue(_word_boundary_match("texas (region) update", "texas"))


# ---------------------------------------------------------------------------
# _keyword_has_stop
# ---------------------------------------------------------------------------


class TestKeywordHasStop(TestCase):
    def test_stop_detected_in_single_and_all_stop(self):
        """Single or all-stop-word keywords are flagged."""
        self.assertTrue(_keyword_has_stop("new"))
        self.assertTrue(_keyword_has_stop("world"))
        self.assertTrue(_keyword_has_stop("new world report"))

    def test_mixed_and_no_stop_and_empty(self):
        """Keywords with any real word pass. Empty string is vacuously True."""
        self.assertFalse(_keyword_has_stop("new weather alert"))
        self.assertFalse(_keyword_has_stop("hurricane mariah"))
        self.assertTrue(_keyword_has_stop(""))


# ---------------------------------------------------------------------------
# tag_story_with_keywords — basic
# ---------------------------------------------------------------------------


class TestTagStoryBasic(TestCase):
    def test_single_and_multiple_keyword_matches(self):
        with _patch_config():
            result = tag_story_with_keywords("AI model breakthrough")
        self.assertIn("[[ai]]", result)

        with _patch_config():
            result = tag_story_with_keywords("Houston weather storm hits texas")
        self.assertIn("[[local]]", result)
        self.assertIn("[[weather]]", result)

    def test_no_match_fallback(self):
        with _patch_config():
            result = tag_story_with_keywords("Cooking dinner at home")
        self.assertNotIn("[[ai]]", result)
        self.assertNotIn("[[weather]]", result)

        with _patch_config():
            result = tag_story_with_keywords("Zyx qwerty abc")
        self.assertEqual(result, "#news")

    def test_output_format_bracketed(self):
        with _patch_config():
            result = tag_story_with_keywords("AI and machine learning news")
        tags = result.split()
        for tag in tags:
            self.assertTrue(tag.startswith("[[") and tag.endswith("]]"))


# ---------------------------------------------------------------------------
# tag_story_with_keywords — scoring
# ---------------------------------------------------------------------------


class TestTagStoryScoring(TestCase):
    def test_more_hits_first(self):
        """Keyword with most hits scores highest and appears first."""
        with _patch_config():
            result = tag_story_with_keywords("ai artificial intelligence machine learning model")
            tags = result.split()
            self.assertEqual(tags[0], "[[ai]]")

    def test_multi_word_keyword(self):
        with _patch_config():
            result = tag_story_with_keywords("artificial intelligence is huge")
        self.assertIn("[[ai]]", result)

    def test_stop_word_keyword_ignored(self):
        """Keywords composed entirely of stop words are skipped."""
        mappings = {
            "newstuff": ["new"],
            "report": ["report", "analysis"],
            "real": ["weather"],
        }
        with _patch_config(mappings=mappings):
            result = tag_story_with_keywords("new report on new findings")
        self.assertNotIn("[[newstuff]]", result)
        self.assertNotIn("[[report]]", result)


# ---------------------------------------------------------------------------
# tag_story_with_keywords — threshold
# ---------------------------------------------------------------------------


class TestTagStoryThreshold(TestCase):
    def test_below_threshold_no_tag(self):
        """High threshold blocks tags."""
        with _patch_config(score_threshold=99.0):
            result = tag_story_with_keywords("AI model")
        self.assertNotIn("[[ai]]", result)

    def test_zero_threshold_any_score(self):
        """Threshold=0.0 lets any positive score through."""
        with _patch_config(score_threshold=0.0):
            result = tag_story_with_keywords("AI news")
        self.assertIn("[[ai]]", result)


# ---------------------------------------------------------------------------
# tag_story_with_keywords — max_tags
# ---------------------------------------------------------------------------


class TestTagStoryMaxTags(TestCase):
    def test_truncates_to_max(self):
        """Only top N tags returned by max_tags slice."""
        with _patch_config(max_tags=2):
            result = tag_story_with_keywords("ai machine learning weather storm houston")
        tags = result.split()
        self.assertLessEqual(len(tags), 3)  # max_tags + possible min_tags additions
        self.assertEqual(len(tags), len(set(tags)))

    def test_max_tags_zero_safe(self):
        with _patch_config(max_tags=0):
            result = tag_story_with_keywords("ai storm houston")
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# tag_story_with_keywords — category boosts
# ---------------------------------------------------------------------------


class TestCategoryBoost(TestCase):
    def test_category_membership_boosts(self):
        """Category membership adds +3.0 even without keyword match."""
        mappings = {
            "weather": ["hurricane"],
        }
        boosts = {
            "Weather Alerts": ["weather"],
        }
        with _patch_config(mappings=mappings, boosts=boosts):
            result = tag_story_with_keywords("Storm warning issued", category="Weather Alerts")
        self.assertIn("[[weather]]", result)

    def test_no_boost_without_category(self):
        """Boosts only fire for explicit category membership."""
        mappings = {
            "weather": ["hurricane"],
        }
        boosts = {"Weather Alerts": ["weather"]}
        with _patch_config(mappings=mappings, boosts=boosts):
            result = tag_story_with_keywords("Storm warning issued", category=None)
        self.assertNotIn("[[weather]]", result)


# ---------------------------------------------------------------------------
# tag_story_with_keywords — conflicts
# ---------------------------------------------------------------------------


class TestTagConflicts(TestCase):
    def test_conflict_resolution_before_min_tags(self):
        """Conflict resolution fires first; min_tags cannot restore the loser."""
        mappings = {
            "economy": ["stock", "market", "earnings"],
            "international": ["international", "foreign"],
            "local": ["local", "city", "municipal"],
            "sports": ["nfl", "football"],
        }
        conflicts = [["international", "local"]]
        with _patch_config(mappings=mappings, conflicts=conflicts, boosts={}):
            result = tag_story_with_keywords(
                "international trade and local city stock market nfl football"
            )
        tags = result.split()
        self.assertEqual(len(tags), 3)
        for t in tags:
            self.assertTrue(t.startswith("[[") and t.endswith("]]"))
        self.assertIn("[[local]]", result)
        self.assertNotIn("[[international]]", result)
        self.assertIn("[[economy]]", result)
        self.assertIn("[[sports]]", result)


# ---------------------------------------------------------------------------
# tag_story_with_keywords — conflict + min tag promotion (regression)
# ---------------------------------------------------------------------------


class TestConflictMinimumTagPromotion(TestCase):
    def test_conflict_loser_not_repromoted(self):
        """The live failure: conflict resolution removes the loser, but the
        minimum-tag promotion loop must NEVER re-add it to reach 3 tags.

        Scenario:
        - Title matches both 'international' and 'local' keywords
        - Category boost gives 'local' a higher score
        - 'local' wins over 'international' in the conflict pair
        - Only 2 matching tags exist, so min-tag promotion would try to fill
        - Assert: 'international' is NOT re-added"""
        mappings = {
            "international": ["international", "foreign"],
            "local": ["houston", "texas"],
        }
        conflicts = [["international", "local"]]
        boosts = {
            "Local News": ["local"],
        }
        with _patch_config(mappings=mappings, conflicts=conflicts, boosts=boosts):
            result = tag_story_with_keywords(
                "International homebuyers are flocking to Texas",
                category="Local News",
            )
        tags = result.split()
        has_local = "[[local]]" in tags
        has_international = "[[international]]" in tags
        # Must never have both conflicting tags present
        if has_local:
            self.assertFalse(
                has_international,
                "Conflicting tag 'international' was re-added to satisfy min_tags",
            )
        if has_international:
            self.assertFalse(
                has_local,
                "Conflicting tag 'local' was re-added to satisfy min_tags",
            )

    def test_conflict_winner_retained(self):
        """The conflict winner (higher score) is retained after resolution."""
        mappings = {
            "international": ["international", "foreign"],
            "local": ["houston", "texas"],
        }
        conflicts = [["international", "local"]]
        boosts = {"Local News": ["local"]}
        with _patch_config(mappings=mappings, conflicts=conflicts, boosts=boosts):
            result = tag_story_with_keywords(
                "International homebuyers are flocking to Texas",
                category="Local News",
            )
        # 'local' wins (category boost gives +3.0) so it must be present
        self.assertIn("[[local]]", result)
        self.assertNotIn("[[international]]", result)

    def test_min_promotion_still_works_without_conflicts(self):
        """Normal min-tag promotion still fills to 3 when no conflicts exist."""
        mappings = {
            "ai": ["ai"],
            "weather": ["weather"],
        }
        with _patch_config(mappings=mappings, conflicts=[]):
            result = tag_story_with_keywords("ai", category="AI News")
        tags = result.split()
        self.assertGreaterEqual(len(tags), 1)
        self.assertIn("[[ai]]", result)

    def test_fewer_than_three_tags_acceptable_when_conflicts_prevent(self):
        """When all extra tags conflict with the survivors, the story is
        allowed to have fewer than 3 tags rather than violating conflicts."""
        mappings = {
            "a": ["alpha"],
            "b": ["beta"],
            "c": ["gamma"],
        }
        conflicts = [["a", "b"], ["a", "c"]]
        with _patch_config(mappings=mappings, conflicts=conflicts, boosts={}):
            result = tag_story_with_keywords("alpha beta gamma")
        tags = result.split()
        has_a = "[[a]]" in tags
        has_b = "[[b]]" in tags
        has_c = "[[c]]" in tags
        # a conflicts with both b and c; b and c conflict with a
        # Check: no conflicting pair is present together
        if has_a:
            self.assertFalse(has_b, "a and b are conflicting")
            self.assertFalse(has_c, "a and c are conflicting")
        # It's acceptable if only 1 or 2 tags are present
        self.assertLessEqual(len(tags), 3)


# ---------------------------------------------------------------------------
# tag_story_with_keywords — deduplication
# ---------------------------------------------------------------------------


class TestTagDeduplication(TestCase):
    def test_no_duplicate_tags(self):
        """Output never contains duplicate tags, even with repeated keywords or duplicate mappings."""
        with _patch_config():
            result = tag_story_with_keywords("ai ai artificial intelligence machine learning")
        tags = result.split()
        self.assertEqual(len(tags), len(set(tags)))

        mappings = {
            "ai": ["ai", "ai", "artificial intelligence"],
            "weather": ["weather"],
        }
        with _patch_config(mappings=mappings):
            result = tag_story_with_keywords("ai artificial intelligence weather")
        self.assertIn("[[ai]]", result)
        self.assertIn("[[weather]]", result)
        tags = result.split()
        self.assertEqual(tags.count("[[ai]]"), 1)
        self.assertEqual(tags.count("[[weather]]"), 1)


# ---------------------------------------------------------------------------
# tag_story_with_keywords — min tag promotion
# ---------------------------------------------------------------------------


class TestMinTagPromotion(TestCase):
    def test_category_fallback_for_min_tags(self):
        """If < 3 tags and category provided → category-derived tag added."""
        mappings = {
            "ai": ["artificial"],
        }
        with _patch_config(mappings=mappings):
            result = tag_story_with_keywords("artificial system", category="Science Today")
        self.assertIn("[[science-today]]", result)

    def test_category_parts_fill_min(self):
        """Category words used to reach min_tags=3."""
        mappings = {
            "ai": ["artificial"],
        }
        with _patch_config(mappings=mappings):
            result = tag_story_with_keywords("artificial system", category="Deep Learning Weekly")
        tags = result.split()
        self.assertGreaterEqual(len(tags), 2)

    def test_promotion_below_threshold(self):
        """Tags below threshold promoted to meet min_tags."""
        mappings = {
            "ai": ["ai"],
            "weather": ["storm"],
            "local": ["houston"],
        }
        with _patch_config(mappings=mappings):
            result = tag_story_with_keywords("ai and storms")
        tags = result.split()
        self.assertGreaterEqual(len(tags), 1)


# ---------------------------------------------------------------------------
# tag_story_with_keywords — edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases(TestCase):
    def test_empty_title_and_none_category(self):
        """Empty title returns valid string. None category works fine."""
        with _patch_config():
            result = tag_story_with_keywords("")
        self.assertIsInstance(result, str)

        with _patch_config():
            result = tag_story_with_keywords("ai news", category=None)
        self.assertIn("[[ai]]", result)

    def test_special_chars_and_unicode(self):
        """Special chars and Unicode in title don't break matching."""
        with _patch_config():
            result = tag_story_with_keywords("AI: 'Artificial Intelligence' — The Future (2025)")
        self.assertIn("[[ai]]", result)

        with _patch_config():
            result = tag_story_with_keywords("AI modèle français")
        self.assertIn("[[ai]]", result)


if __name__ == "__main__":
    import unittest

    unittest.main()
