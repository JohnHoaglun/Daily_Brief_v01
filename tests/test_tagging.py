"""Reduced: tag conflict policy and successful tagging."""

from contextlib import contextmanager
from unittest import TestCase, mock

from daily_brief.tagging import (
    _word_boundary_match,
    tag_story_with_keywords,
)

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
def _patch_config(mappings=None, boosts=None, conflicts=None, score_threshold=0.3):
    patches = [
        mock.patch("daily_brief.tagging.TAGGING_MAPPINGS", mappings or _DEFAULT_MAPPINGS),
        mock.patch("daily_brief.tagging.CATEGORY_BOOSTS", boosts or _DEFAULT_BOOSTS),
        mock.patch("daily_brief.tagging.TAG_CONFLICTS", conflicts or _DEFAULT_CONFLICTS),
        mock.patch("daily_brief.tagging.TAGGING_CONFIG", {"max_tags": 5, "score_cap": 5.0, "score_threshold": score_threshold}),
        mock.patch("daily_brief.tagging.FRONTMATTER_FALLBACK_TAG", "#news"),
    ]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in reversed(patches):
            p.stop()


class TestSuccessfulTagging(TestCase):
    def test_successful_tag_match(self):
        with _patch_config():
            result = tag_story_with_keywords("AI model breakthrough")
        self.assertIn("[[ai]]", result)

    def test_multiple_matching_tags(self):
        with _patch_config():
            result = tag_story_with_keywords("Houston weather storm hits texas")
        self.assertIn("[[local]]", result)
        self.assertIn("[[weather]]", result)

    def test_output_format_bracketed(self):
        with _patch_config():
            result = tag_story_with_keywords("AI and machine learning news")
        for tag in result.split():
            self.assertTrue(tag.startswith("[[") and tag.endswith("]]"))

    def test_no_match_returns_fallback(self):
        with _patch_config():
            result = tag_story_with_keywords("Zyx qwerty abc")
        self.assertEqual(result, "#news")

    def test_stop_word_keyword_ignored(self):
        mappings = {"newstuff": ["new"], "report": ["report", "analysis"], "real": ["weather"]}
        with _patch_config(mappings=mappings):
            result = tag_story_with_keywords("new report on new findings")
        self.assertNotIn("[[newstuff]]", result)
        self.assertNotIn("[[report]]", result)


class TestTagConflictPolicy(TestCase):
    def test_conflict_resolution(self):
        mappings = {
            "economy": ["stock", "market"],
            "international": ["international"],
            "local": ["local", "city"],
            "sports": ["nfl", "football"],
        }
        conflicts = [["international", "local"]]
        with _patch_config(mappings=mappings, conflicts=conflicts, boosts={}):
            result = tag_story_with_keywords(
                "international trade and local city stock market nfl football"
            )
        tags = result.split()
        has_local = "[[local]]" in tags
        has_international = "[[international]]" in tags
        if has_local:
            self.assertFalse(has_international, "Conflicting tag 'international' should not appear")
        if has_international:
            self.assertFalse(has_local, "Conflicting tag 'local' should not appear")

    def test_conflict_loser_not_repromoted(self):
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
        tags = result.split()
        has_local = "[[local]]" in tags
        has_international = "[[international]]" in tags
        if has_local:
            self.assertFalse(has_international, "Conflict loser 'international' must not be repromoted")

    def test_conflict_winner_retained(self):
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
        self.assertIn("[[local]]", result)
        self.assertNotIn("[[international]]", result)

    def test_min_promotion_without_conflicts(self):
        mappings = {"ai": ["ai"], "weather": ["weather"]}
        with _patch_config(mappings=mappings, conflicts=[]):
            result = tag_story_with_keywords("ai", category="AI News")
        self.assertIn("[[ai]]", result)


class TestWordBoundaryMatch(TestCase):
    def test_exact_and_case_insensitive(self):
        self.assertTrue(_word_boundary_match("ai breakthrough", "ai"))
        self.assertTrue(_word_boundary_match("AI takes over", "ai"))

    def test_no_partial_match(self):
        self.assertFalse(_word_boundary_match("stunning performance", "sting"))
        self.assertFalse(_word_boundary_match("stunning results", "sun"))


if __name__ == "__main__":
    import unittest
    unittest.main()
