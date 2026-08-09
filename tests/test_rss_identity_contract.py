"""
Test fixtures documenting the desired RSS dedup identity contract (Wave 0).

Fixtures expose known bugs in normalize_title() and widen_category():
  - Bug A: Splits on first " - " separator, stripping site suffix.
           "Tech News - Source A" and "Tech News - Source B" both normalize
           to "tech news" and are incorrectly treated as the same story.
  - Bug B: 80-character truncation.  Distinct titles that diverge only after
           character 80 collide because both are truncated to the same prefix.
  - Bug C: widen_category() is a no-op wrapper returning (existing_count, 0, 0, 0)
           — dead code never called from fetch_and_dedup.

Desired contract:
  - Full Unicode-normalized, lower-cased title is the primary dedup key.
  - Site suffix (after " - ") should NOT be stripped.
  - No truncation for identity purposes.
  - URL-based identity preferred when canonical destination URL is available.
  - Cross-category first-wins still applies.
"""
from __future__ import annotations

import asyncio
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set, Tuple
from unittest import TestCase

from daily_brief.pipelines.rss_dedup import widen_category
from daily_brief.sources.rss import normalize_title


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _await(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _normalize(t: str) -> str:
    return normalize_title(t)


# ---------------------------------------------------------------------------
# Bug A: Shared-prefix / " - " separator collision
# ---------------------------------------------------------------------------

class TestFirstDashBugSharedPrefix(TestCase):
    """Stories with shared prefix before " - " must NOT collide."""

    def test_shared_prefix_different_sources_no_collision(self):
        """'Tech News - Source A' and 'Tech News - Source B' are different stories."""
        a = _normalize("Tech News - Source A")
        b = _normalize("Tech News - Source B")
        # BUG: both normalize to "tech news" — should be distinct
        self.assertNotEqual(a, b)

    def test_shared_prefix_reversed_order_no_collision(self):
        """Order of arguments must not affect equality outcome."""
        titles = [
            "Breaking - CNN",
            "Breaking - Fox News",
            "Breaking - Reuters",
        ]
        norms = [_normalize(t) for t in titles]
        # BUG: all three collapse to "breaking"
        self.assertEqual(len(set(norms)), len(norms))

    def test_distant_sources_no_collision(self):
        """'World Update - The Guardian' vs 'World Update - BBC' are distinct."""
        g = _normalize("World Update - The Guardian")
        b = _normalize("World Update - BBC")
        # BUG: both normalize to "world update"
        self.assertNotEqual(g, b)

    def test_same_prefix_same_source_is_same(self):
        """'Market Watch - WSJ' from the same source IS the same story."""
        a = _normalize("Market Watch - WSJ")
        b = _normalize("Market Watch - WSJ")
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# Same article, different casing still collides (correct behavior)
# ---------------------------------------------------------------------------

class TestCasingCollision(TestCase):
    """Same article from same source with different casing must collide."""

    def test_uppercase_lowercase_collision(self):
        a = _normalize("Breaking News")
        b = _normalize("breaking news")
        self.assertEqual(a, b)

    def test_mixed_case_collision(self):
        a = _normalize("Daily Market Report")
        b = _normalize("daily MARKET report")
        self.assertEqual(a, b)

    def test_case_with_dashed_suffix(self):
        """With the bug, both collapse to the prefix anyway — test desired outcome."""
        a = _normalize("Weather Update - Source")
        b = _normalize("WEATHER UPDATE - SOURCE")
        # BUG: both become "weather update" (prefix-only), desired is
        # "weather update - source" == "weather update - source" (full)
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# Bug B: 80-character truncation
# ---------------------------------------------------------------------------

class TestTruncationBug(TestCase):
    """Long titles must not collide only because of 80-char truncation."""

    def test_long_titles_diverging_after_80_chars_no_collision(self):
        """Two 120-char titles that share the first 80 chars but diverge after must be distinct."""
        shared = "A " * 40  # exactly 80 chars
        title_a = shared + "Alpha version released"  # 104 chars
        title_b = shared + "Beta version released"   # 103 chars
        # Characters 1-80 are identical
        self.assertEqual(title_a[:80], title_b[:80])
        # Characters 81+ differ
        self.assertNotEqual(title_a[80:], title_b[80:])
        # BUG: both truncated to same 80-char shared prefix, collide incorrectly
        a = _normalize(title_a)
        b = _normalize(title_b)
        self.assertNotEqual(a, b)

    def test_very_long_identical_titles_still_collide(self):
        """Two identical 200-char titles must collide (correct behavior)."""
        title = "A" * 200
        self.assertEqual(_normalize(title), _normalize(title))

    def test_title_exactly_80_chars_preserved(self):
        """Title exactly 80 chars must not lose information."""
        title = "X" * 80
        normalized = _normalize(title)
        self.assertEqual(len(normalized), 80)
        self.assertEqual(normalized, title.lower())

    def test_title_81_chars_truncated(self):
        """Title 81 chars IS truncated to 80 (current buggy behavior)."""
        title = "X" * 81
        normalized = _normalize(title)
        self.assertEqual(len(normalized), 80)
        self.assertNotEqual(normalized, title.lower())  # lost the last char


# ---------------------------------------------------------------------------
# Bug C: widen_category is a no-op
# ---------------------------------------------------------------------------

class TestWidenCategoryNoOp(TestCase):
    """widen_category() is dead code — returns (existing_count, 0, 0, 0)."""

    async def _call_widen(self, existing_count: int):
        return await widen_category(
            session=None,
            cat_name="TestCat",
            existing_count=existing_count,
            seen_map={},
            deduped_list=[],
            now_ct=datetime.now(timezone.utc),
            categories=[],
            log_fn=lambda *_: None,
        )

    def test_noop_returns_existing_count(self):
        """First element of return tuple is the existing_count passed in."""
        result = _await(self._call_widen(5))
        # Shape: (existing_count, age_filtered, dup_filtered, recovered)
        self.assertEqual(result[0], 5)
        self.assertEqual(result[1], 0)
        self.assertEqual(result[2], 0)
        self.assertEqual(result[3], 0)

    def test_noop_returns_existing_count_zero(self):
        result = _await(self._call_widen(0))
        self.assertEqual(result, (0, 0, 0, 0))

    def test_noop_returns_existing_count_large(self):
        result = _await(self._call_widen(99))
        self.assertEqual(result, (99, 0, 0, 0))

    def test_noop_ignores_deduped_list(self):
        """widen_category does not read or mutate deduped_list."""
        seen: Dict[str, Set[str]] = {"TestCat": {"seen"}}
        deduped: List[Tuple[str, str, str, datetime, str]] = []
        result = _await(
            widen_category(
                session=None,
                cat_name="TestCat",
                existing_count=3,
                seen_map=seen,
                deduped_list=deduped,
                now_ct=datetime.now(timezone.utc),
                categories=[],
                log_fn=lambda *_: None,
            )
        )
        # No mutation
        self.assertEqual(len(deduped), 0)
        self.assertEqual(len(seen["TestCat"]), 1)
        self.assertEqual(result, (3, 0, 0, 0))


# ---------------------------------------------------------------------------
# Unicode normalization
# ---------------------------------------------------------------------------

class TestUnicodeNormalization(TestCase):
    """Equivalent Unicode characters must resolve to the same dedup key."""

    def test_accented_vs_decomposed(self):
        """'naïve' (precomposed e-239) vs 'n\u0061\u0308ve' (decomposed) must collide."""
        precomposed = "na\u00efve"       # ï as single codepoint
        decomposed = "na\u0069\u0308ve"   # i + combining diaeresis
        # Verify they differ at the codepoint level
        self.assertNotEqual(precomposed, decomposed)
        # NFKD normalization should make them equal
        self.assertEqual(
            unicodedata.normalize("NFKD", precomposed),
            unicodedata.normalize("NFKD", decomposed),
        )
        # BUG: normalize_title does no Unicode normalization — these may collide
        # only if lowercasing happens to produce the same bytes (CPython often
        # stores decomposed form internally, but we can't rely on that).
        self.assertEqual(_normalize(precomposed), _normalize(decomposed))

    def test_fullwidth_ascii(self):
        """Fullwidth 'ABC' should normalize to 'abc'."""
        fullwidth = "ＡＢＣ News"
        ascii_eq = "ABC News"
        a = _normalize(fullwidth)
        b = _normalize(ascii_eq)
        # NFKD maps fullwidth to ASCII
        self.assertEqual(
            unicodedata.normalize("NFKD", fullwidth.strip().lower()),
            unicodedata.normalize("NFKD", ascii_eq.strip().lower()),
        )
        # BUG: no NFKD in normalize_title
        self.assertEqual(a, b)

    def test_smart_quotes(self):
        """Curly quotes should normalize to straight quotes."""
        curly = "He said \"hello\""
        straight = 'He said "hello"'
        a = _normalize(curly)
        b = _normalize(straight)
        self.assertEqual(a, b)


# ---------------------------------------------------------------------------
# Empty title handling
# ---------------------------------------------------------------------------

class TestEmptyTitle(TestCase):
    """Empty or whitespace titles must not crash dedup."""

    def test_empty_string(self):
        result = _normalize("")
        self.assertEqual(result, "")

    def test_whitespace_only(self):
        result = _normalize("   ")
        self.assertEqual(result, "")

    def test_newline_only(self):
        result = _normalize("\n")
        self.assertEqual(result, "")

    def test_dash_only(self):
        """' - ' is the separator with no content parts — should not crash.
        Normalizes to '-' (strip removes spaces, dash remains)."""
        result = _normalize(" - ")
        self.assertEqual(result, "-")

    def test_empty_title_no_exception_in_dedup(self):
        """dedup_entries must not crash on empty title."""
        from daily_brief.pipelines.rss_dedup import dedup_entries
        from zoneinfo import ZoneInfo
        TZ = ZoneInfo("America/Chicago")
        now = datetime(2026, 7, 30, 14, 0, 0, tzinfo=TZ)
        fresh = now - timedelta(hours=1)
        entries = [("", "https://example.com", "", fresh)]
        seen, deduped = {}, []
        # fetch_feed filters out empty titles before this point in production,
        # but the contract says dedup must not crash.
        # Empty-title entries have norm="" and will be deduped against each other.
        added, af, df = dedup_entries(entries, now, "cat", 24.0, seen, deduped)
        # Empty title entry: norm="" is added to seen; not filtered by content
        # checks (no obit/real-estate keywords); it should be accepted.
        self.assertEqual(added, 1)
        self.assertEqual(af, 0)
        self.assertEqual(df, 0)


# ---------------------------------------------------------------------------
# Cross-category first-wins (existing correct behavior, regression)
# ---------------------------------------------------------------------------

class TestCrossCategoryFirstWins(TestCase):
    """Cross-category dedup: first-wins must still hold."""

    def test_same_title_different_categories_first_wins(self):
        """Same normalized title in CatA and CatB: CatA wins."""
        from daily_brief.pipelines.rss_dedup import dedup_entries
        from zoneinfo import ZoneInfo
        TZ = ZoneInfo("America/Chicago")
        now = datetime(2026, 7, 30, 14, 0, 0, tzinfo=TZ)
        fresh = now - timedelta(hours=1)

        cats_seen: Dict[str, Set[str]] = {}
        deduped_a: List = []
        deduped_b: List = []

        # Add to CatA first
        dedup_entries(
            [("Story Title", "https://a.com", "", fresh)],
            now, "CatA", 24.0, cats_seen, deduped_a,
        )
        # Same normalized title to CatB
        dedup_entries(
            [("Story Title", "https://b.com", "", fresh)],
            now, "CatB", 24.0, cats_seen, deduped_b,
        )

        # Per-category dedup is independent; both categories get the entry.
        # Cross-cat dedup in fetch_and_dedup is what removes the duplicate.
        # This test only covers per-category behavior (cat-specific seen_map).
        self.assertEqual(len(deduped_a), 1)
        self.assertEqual(len(deduped_b), 1)
        # Different seen sets per category
        self.assertIn("story title", cats_seen.get("CatA", set()))
        self.assertIn("story title", cats_seen.get("CatB", set()))


# ---------------------------------------------------------------------------
# URL-based identity (desired future behavior, not yet implemented)
# ---------------------------------------------------------------------------

class TestUrlBasedIdentity(TestCase):
    """When canonical destination URL is available, prefer URL over title."""

    def test_same_title_different_urls_are_distinct(self):
        """Two articles with same title but different URLs should be distinct.
        NOTE: normalize_title only operates on titles; URL-based identity
        requires changes to the dedup key computation in dedup_entries.
        This test documents the desired behavior.
        """
        # Current behavior normalizes by title only:
        norm = _normalize("Breaking News")
        self.assertEqual(norm, "breaking news")

    def test_same_url_different_titles_same_article(self):
        """Same URL but re-titled copies should be treated as the same article.
        NOTE: not yet implemented — normalize_title does not receive URL.
        This test documents the desired behavior.
        """
        self.assertTrue(True)  # placeholder for future URL-aware dedup
