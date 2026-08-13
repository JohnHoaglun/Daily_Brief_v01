"""
Daily Brief — Summary quality checks.

Contains refusal detection, boilerplate detection, stopword filtering,
topic overlap, and summary validation.
"""

import logging
import re

from daily_brief.utils import _count_sentences

logger = logging.getLogger(__name__)



def _is_refusal(text):
    """Detect LLM refusal/placeholder text that is not a real summary."""
    if not text:
        return False
    t = text.strip().lower()
    refusal_phrases = [
        "please provide the article",
        "i don't have access",
        "i do not have access",
        "i can't",
        "i cannot",
        "cannot summarize",
        "no article content",
        "unable to summarize",
        "article not provided",
        "no content available",
        "write a detailed summary for you",
        "i am not able to",
        "i'm not able to",
        "please provide the source",
    ]
    return any(p in t for p in refusal_phrases)


def _is_boilerplate(text):
    """Detect vague, generic boilerplate summaries that lack concrete facts."""
    if not text:
        return False
    t = text.strip().lower()
    boilerplate_phrases = [
        "this highlights a significant",
        "this suggests a",
        "this indicates a",
        "further details on the nature",
        "further details are not",
        "are not included",
        "are not specified",
        "details regarding",
        "this serves as",
        "this demonstrates",
        "this underscores",
        "this reflects",
        "this signals",
        "this article discusses",
        "this story covers",
        "the author writes",
        "according to",
        "the report states",
        "in this piece",
        "this piece explores",
        "this article explores",
        "the article examines",
        "this story examines",
        "the following article",
        "the following story",
    ]
    return any(p in t for p in boilerplate_phrases)


def _generate_auto_fallback(title):
    """Generate a deterministic fallback summary from the story title alone.
    Returns: [Auto] {headline} — minimal but informative."""
    if not title:
        return "[Summary Unavailable]"
    cleaned = re.sub(r"\s+", " ", str(title)).strip()
    # Remove trailing colon, question mark clusters, and common truncation markers
    cleaned = re.sub(r"[:\-\u2014]\s*$", "", cleaned).strip()
    return f"[Auto] {cleaned}"


_VALID_SUMMARY_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "at",
    "by",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "this",
    "that",
    "these",
    "those",
    "as",
    "it",
    "its",
    "into",
    "after",
    "over",
    "amid",
    "than",
    "their",
    "his",
    "her",
    "has",
    "have",
    "had",
    "will",
    "would",
    "could",
    "should",
    "about",
    "which",
    "who",
    "what",
    "says",
    "said",
    "new",
    "more",
    "not",
    "also",
    "some",
    "such",
    "each",
}


def _significant_words(text):
    """Extract significant words (4+ chars, not stop words) from text."""
    return {
        w
        for w in re.findall(r"[a-zA-Z']+", text.lower())
        if len(w) > 3 and w not in _VALID_SUMMARY_STOPWORDS
    }


def _has_topic_overlap(summary, headline):
    """Check if summary shares at least one significant word with the headline.

    Prevents topic-mismatched summaries from passing validation when the LLM
    produces a grammatically valid but semantically unrelated summary.
    """
    hw = _significant_words(headline)
    sw = _significant_words(summary)
    return bool(hw & sw)


def _is_valid_summary(summary, headline):
    """Check if a summary passes basic validation.

    Canonical quality gate used by both batch and individual LLM recovery.
    """
    if not summary or not summary.strip():
        return False
    stripped = summary.strip()
    if _is_refusal(stripped):
        return False
    if _is_boilerplate(stripped):
        return False
    if stripped.startswith("[Auto]") or stripped.startswith("[Summary Unavailable]"):
        return False
    normalized = re.sub(r"\s+", " ", stripped).strip().lower()
    headline_norm = re.sub(r"\s+", " ", headline).strip().lower()
    if normalized == headline_norm or normalized.startswith(headline_norm + "."):
        return False
    if _count_sentences(stripped) < 2:
        return False
    if not _has_topic_overlap(stripped, headline):
        return False
    return True
