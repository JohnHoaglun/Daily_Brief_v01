"""Test fixtures documenting the desired RSS dedup identity contract (Wave 0)."""

from __future__ import annotations

from unittest import TestCase

from daily_brief.sources.rss import normalize_title


def _normalize(t: str) -> str:
    return normalize_title(t)


class TestSharedPrefixCollisionBug(TestCase):
    """Shared-prefix titles with different sources must NOT collide after ' - '."""

    def test_tech_news_different_sources(self):
        """'Tech News - Source A' and 'Tech News - Source B' are different stories."""
        a = _normalize("Tech News - Source A")
        b = _normalize("Tech News - Source B")
        self.assertNotEqual(a, b)

    def test_multiple_sources_all_distinct(self):
        titles = [
            "Breaking - CNN",
            "Breaking - Fox News",
            "Breaking - Reuters",
        ]
        norms = [_normalize(t) for t in titles]
        self.assertEqual(len(set(norms)), len(norms))


class TestNoTruncation(TestCase):
    """Long titles that diverge after 80 chars must not collide via truncation."""

    def test_diverge_after_80_chars(self):
        shared = "A " * 40
        title_a = shared + "Alpha version released"
        title_b = shared + "Beta version released"
        self.assertEqual(title_a[:80], title_b[:80])
        self.assertNotEqual(title_a[80:], title_b[80:])
        a = _normalize(title_a)
        b = _normalize(title_b)
        self.assertNotEqual(a, b)

    def test_81_chars_preserved(self):
        title = "X" * 81
        normalized = _normalize(title)
        self.assertEqual(len(normalized), 81)
        self.assertEqual(normalized, title.lower())
