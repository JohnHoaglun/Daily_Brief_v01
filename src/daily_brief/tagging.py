import re
import logging

from config import (
    TAGGING_MAPPINGS,
    TAGGING_CONFIG,
    CATEGORY_BOOSTS,
    FRONTMATTER_FALLBACK_TAG,
    TAG_CONFLICTS,
)

logger = logging.getLogger(__name__)

# Words that are always matched away — never count them toward a tag score.
_STOP_WORDS = {
    "new", "newly", "news", "novel",
    "world", "global", "globals",
    "first",
    "report",
    "analysis",
}


def _word_boundary_match(text, keyword):
    """Return True when *keyword* appears as a whole word in *text*."""
    pat = r"(?<![a-zA-Z])" + re.escape(keyword) + r"(?![a-zA-Z])"
    return bool(re.search(pat, text, re.IGNORECASE))


def _keyword_has_stop(keyword):
    """Quick check: does the keyword consist entirely of stop words?"""
    words = re.findall(r"\b[a-z]+\b", keyword.lower())
    return all(w in _STOP_WORDS for w in words)


def tag_story_with_keywords(story_title, category=None):
    """Generate meaningful tags for a story based on its title using keyword matching.

    Rules applied:
    * Whole-word (boundary) matching — avoids "world" inside "stunning".
    * Stop-word filter — keywords made only of stop words are ignored.
    * Mutual-exclusion conflicts — e.g. international vs us-focused.
    """
    keywords_to_tags = TAGGING_MAPPINGS or {}
    max_tags = int(TAGGING_CONFIG.get("max_tags", 5))
    score_cap = float(TAGGING_CONFIG.get("score_cap", 5.0))
    score_threshold = float(TAGGING_CONFIG.get("score_threshold", 0.3))
    category_boosts = CATEGORY_BOOSTS or {}
    tag_conflicts = TAG_CONFLICTS or []

    title_lower = story_title.lower()
    tag_scores = {}

    for tag, keywords in keywords_to_tags.items():
        if not keywords:
            continue
        score = 0.0
        for keyword in keywords:
            if not keyword:
                continue

            if _keyword_has_stop(keyword):
                continue

            if _word_boundary_match(title_lower, keyword):
                pos = title_lower.find(keyword)
                if pos >= 0:
                    boost = 2.0 if pos < 100 else 1.0
                    word_count = len([w for w in keyword.split() if w not in _STOP_WORDS])
                    score += boost * max(word_count, 1)

        # Category boosts
        if category and category in category_boosts:
            for bkeyword in category_boosts[category]:
                if not _keyword_has_stop(bkeyword) and _word_boundary_match(title_lower, bkeyword):
                    score += 2.0

        if score > score_threshold:
            tag_scores[tag] = min(score, score_cap)

    sorted_tags = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
    tag_list = [tag for tag, _ in sorted_tags[:max_tags]]

    # Resolve mutually exclusive tag conflicts
    if tag_conflicts:
        for pair in tag_conflicts:
            if len(pair) != 2:
                continue
            a, b = pair
            if a in tag_scores and b in tag_scores:
                loser = a if tag_scores.get(a, 0) <= tag_scores.get(b, 0) else b
                tag_list = [t for t in tag_list if t != loser]

    if not tag_list and category:
        category_tag = category.lower().replace(" ", "-").replace("/", "-")
        tag_list = [category_tag]

    formatted_tags = ["[[%s]]" % tag for tag in tag_list]
    return " ".join(formatted_tags) if formatted_tags else FRONTMATTER_FALLBACK_TAG
