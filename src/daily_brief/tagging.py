import logging

from config import TAGGING_MAPPINGS, TAGGING_CONFIG, CATEGORY_BOOSTS, FRONTMATTER_FALLBACK_TAG

logger = logging.getLogger(__name__)


def tag_story_with_keywords(story_title, category=None):
    """Generate meaningful tags for a story based on its title using keyword matching.

    Reads keyword mappings from TAGGING_CONFIG and TAGGING_MAPPINGS in config.py.
    """
    keywords_to_tags = TAGGING_MAPPINGS or {}
    max_tags = int(TAGGING_CONFIG.get("max_tags", 5))
    score_cap = float(TAGGING_CONFIG.get("score_cap", 5.0))
    category_boosts = CATEGORY_BOOSTS or {}

    title_lower = story_title.lower()
    tag_scores = {}

    for tag, keywords in keywords_to_tags.items():
        score = 0.0
        for keyword in keywords:
            if keyword in title_lower:
                pos = title_lower.find(keyword)
                if pos >= 0:
                    boost = 2.0 if pos < 100 else 1.0
                    score += boost * (1.0 / len(keyword))

        if category and category in category_boosts:
            for keyword in category_boosts[category]:
                if keyword in title_lower:
                    score += 2.0

        if score > 0:
            tag_scores[tag] = min(score, score_cap)

    sorted_tags = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
    tag_list = [tag for tag, _ in sorted_tags[:max_tags]]

    if not tag_list and category:
        category_tag = category.lower().replace(" ", "-").replace("/", "-")
        tag_list = [category_tag]

    formatted_tags = ["[[%s]]" % tag for tag in tag_list]
    return " ".join(formatted_tags) if formatted_tags else FRONTMATTER_FALLBACK_TAG
