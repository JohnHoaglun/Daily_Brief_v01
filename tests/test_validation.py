"""
Direct tests for validate_stories() in daily_brief.validation.

Phase 3D story validation — covers every per-story rule and the 10%
threshold without mocking the function.
"""

from unittest import TestCase

from daily_brief.models import Story
from daily_brief.validation import validate_stories


def _story(title, summary=""):
    """Thin factory for quick inline construction."""
    return Story(title=title, summary=summary)


class TestValidateStories(TestCase):
    """Rule-level and threshold behavior."""

    def test_empty_collection(self):
        """Empty list must return (False, ['Empty story collection'])."""
        passed, issues = validate_stories([])
        self.assertFalse(passed)
        self.assertEqual(issues, ["Empty story collection"])

    def test_valid_two_sentence_summary(self):
        """Valid summary passes immediately."""
        passed, issues = validate_stories([
            _story(
                title="Transit expansion begins",
                summary=(
                    "Transit agencies will begin construction on the new line. "
                    "Funding is now secured."
                ),
            )
        ])
        self.assertTrue(passed)
        self.assertEqual(issues, [])

    def test_empty_summary(self):
        """Empty summary is invalid."""
        passed, issues = validate_stories([
            _story(title="Test headline", summary=""),
        ])
        self.assertFalse(passed)
        assert any("Empty summary for: Test headline" in i for i in issues)

    def test_whitespace_only_summary(self):
        """Whitespace-only summary is invalid, same as empty."""
        passed, issues = validate_stories([
            _story(title="Test headline", summary="   "),
        ])
        self.assertFalse(passed)
        assert any("Empty summary for: Test headline" in i for i in issues)

    def test_headline_echo(self):
        """Exact headline echo in summary is invalid."""
        passed, issues = validate_stories([
            _story(
                title="Local council votes on budget reform",
                summary="Local council votes on budget reform",
            ),
        ])
        self.assertFalse(passed)
        assert any("Summary repeats headline" in i for i in issues)

    def test_headline_echo_with_trailing_period(self):
        """Headline echo with trailing '.' is also invalid."""
        passed, issues = validate_stories([
            _story(
                title="Local council votes on budget reform",
                summary="Local council votes on budget reform.",
            ),
        ])
        self.assertFalse(passed)
        assert any("Summary repeats headline" in i for i in issues)

    def test_too_few_sentences(self):
        """Fewer than two sentences is invalid."""
        passed, issues = validate_stories([
            _story(
                title="Houston transit expansion breaks ground",
                summary="The city begins construction on the rail line.",
            ),
        ])
        self.assertFalse(passed)
        assert any("Too short" in i for i in issues)

    def test_headline_fallback_marker(self):
        """[Headline] prefix in summary is invalid (multi-sentence summary)."""
        passed, issues = validate_stories([
            _story(
                title="Test headline",
                summary="[Headline] This is just a repeat. More text here.",
            ),
        ])
        self.assertFalse(passed)
        assert any("Fallback marker present" in i for i in issues)

    def test_summary_unavailable_marker(self):
        """[summary unavailable] in summary is invalid (multi-sentence summary)."""
        passed, issues = validate_stories([
            _story(
                title="Test headline",
                summary="[summary unavailable] Another sentence. More text here.",
            ),
        ])
        self.assertFalse(passed)
        assert any("Fallback marker present" in i for i in issues)

    def test_auto_exempt_from_all_rules(self):
        """[Auto] summaries bypass headline echo, short text, and topic checks."""
        passed, issues = validate_stories([
            _story(
                title="Houston transit officials approve rail expansion plan",
                summary="[Auto] Houston transit officials approve rail expansion plan",
            ),
        ])
        self.assertTrue(passed)
        self.assertEqual(issues, [])

    def test_auto_exempt_from_topic_mismatch(self):
        """[Auto] is exempt even when the summary has zero topic overlap."""
        passed, issues = validate_stories([
            _story(
                title="Houston transit officials approve rail expansion plan",
                summary="[Auto] The weather is nice today.",
            ),
        ])
        self.assertTrue(passed)
        self.assertEqual(issues, [])

    def test_topic_mismatch_below_threshold(self):
        """Summaries with less than 25% topic overlap are invalid."""
        passed, issues = validate_stories([
            _story(
                title="Federal Reserve raises interest rates",
                summary="New park opens in downtown district. Families enjoy the space.",
            ),
        ])
        self.assertFalse(passed)
        assert any("Topic mismatch" in i for i in issues)

    def test_topic_overlap_at_exactly_25pct_passes(self):
        """25% overlap is the boundary — less fails, equal passes."""
        # Title with 4 significant words, summary shares exactly 1 -> 25%
        passed, issues = validate_stories([
            _story(
                title="Local builds bridge river",
                summary="Officials announced the bridge project. Construction continues.",
            ),
        ])
        self.assertTrue(passed)
        self.assertEqual(issues, [])

    def test_ten_stories_one_invalid_passes(self):
        """1 invalid out of 10 = 10%, which passes the <= 10% threshold."""
        stories = [
            _story(
                title=f"Market report for {i}",
                summary=(
                    f"Market report details are developing. Analysts follow the news "
                    f"carefully. More data continues."
                ),
            )
            for i in range(10)
        ]
        stories[3] = _story(title="Bad story", summary="  ")
        passed, issues = validate_stories(stories)
        self.assertTrue(passed)
        assert any("Empty summary for: Bad story" in i for i in issues)

    def test_ten_stories_two_invalid_fails(self):
        """2 invalid out of 10 = 20%, which exceeds the 10% threshold."""
        stories = [
            _story(
                title=f"Market report for {i}",
                summary=(
                    f"Market report details are developing. Analysts follow the news "
                    f"carefully. More data continues."
                ),
            )
            for i in range(10)
        ]
        stories[3] = _story(title="Bad story", summary="  ")
        stories[7] = _story(title="Also bad", summary="  ")
        passed, issues = validate_stories(stories)
        self.assertFalse(passed)
        assert any("Empty summary for: Bad story" in i for i in issues)
        assert any("Empty summary for: Also bad" in i for i in issues)

    def test_mixed_auto_and_valid_passes(self):
        """Mix of [Auto] and valid summaries passes."""
        passed, issues = validate_stories([
            _story(
                title="Tech company launches new product",
                summary="Tech company unveiled the latest innovation. Sales begin next week.",
            ),
            _story(title="Market update", summary="[Auto] Market update for today"),
            _story(
                title="Local events draw huge crowd",
                summary="Thousands gathered for a local festival. Organizers praise the crowd turnout.",
            ),
        ])
        self.assertTrue(passed)
        self.assertEqual(issues, [])

    def test_mildly_excessive_space_preserves_echo(self):
        """Extra whitespace between words still triggers headline echo."""
        passed, issues = validate_stories([
            _story(
                title="Budget debate heats up",
                summary="Budget   debate  heats  up",
            ),
        ])
        self.assertFalse(passed)
        assert any("Summary repeats headline" in i for i in issues)

if __name__ == "__main__":
    import unittest

    unittest.main()
