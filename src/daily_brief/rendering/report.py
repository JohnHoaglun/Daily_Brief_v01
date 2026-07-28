import logging
import os
from datetime import datetime, timezone

from daily_brief.rendering.weather_table import build_weather_markdown
from daily_brief.tagging import tag_story_with_keywords


logger = logging.getLogger(__name__)


def build_markdown(stories, weather, sections_map, ordered_cats, config_kwargs):
    """Render the full markdown report as a list of strings.

    Args:
        stories: list of StoryPipelineState objects
        weather: weather dict
        sections_map: dict mapping category name to list of story dicts
            (each with "title", "link", "summary", "pub_date")
        ordered_cats: list of category names in render order
        config_kwargs: dict with keys:
            - total_after_dedup
            - rendered_cat_count
            - DEFAULT_CONTENT_AGE_WINDOW_HOURS
            - FRONTMATTER_TAG_SEEDS
            - WEATHER_SECTION_TITLE

    Returns:
        list of md strings
    """
    total_after_dedup = config_kwargs["total_after_dedup"]
    rendered_cat_count = config_kwargs["rendered_cat_count"]
    DEFAULT_CONTENT_AGE_WINDOW_HOURS = config_kwargs["DEFAULT_CONTENT_AGE_WINDOW_HOURS"]
    FRONTMATTER_TAG_SEEDS = config_kwargs["FRONTMATTER_TAG_SEEDS"]
    WEATHER_SECTION_TITLE = config_kwargs["WEATHER_SECTION_TITLE"]

    now = datetime.now(timezone.utc)

    md = []
    md.append("---")
    md.append("title: Daily Brief")
    md.append(f"date: {now.strftime('%Y-%m-%d')}")
    md.append(f"time_generated: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    md.append("status: active")
    md.append(f"content_age_window: {DEFAULT_CONTENT_AGE_WINDOW_HOURS}")
    md.append(f"story_count_total: {total_after_dedup}")
    md.append(f"categories: {rendered_cat_count}")

    # Create a set to collect all unique tags from story titles
    all_tags = set(FRONTMATTER_TAG_SEEDS or [])

    # Process category sections to extract story tags for frontmatter
    for cn in ordered_cats:
        cat_stories = sections_map.get(cn, [])
        for st in cat_stories:
            if "title" in st and st["title"]:
                title = st["title"]
                story_tags = tag_story_with_keywords(title, cn)
                individual_tags = []
                for tag in story_tags.split():
                    tag = tag.strip()
                    if tag.startswith("#"):
                        individual_tags.append(tag.lstrip("#"))
                    elif tag.startswith("[") and tag.endswith("]"):
                        tag_content = tag[2:-2]
                        individual_tags.append(tag_content)
                for tag in individual_tags:
                    all_tags.add(tag.lower())

    # Add tags to YAML frontmatter
    md.append("tags:")
    sorted_tags = sorted(list(all_tags))
    for tag in sorted_tags:
        md.append(f"  - {tag}")

    md.append("---")
    md.append("")
    md.append(f"# Daily Brief -- {now.strftime('%B %d, %Y')}")
    md.extend(build_weather_markdown(weather))

    # Category sections — skip empty categories
    for cn in ordered_cats:
        if cn == WEATHER_SECTION_TITLE or cn == "Weather Forecast 77316":
            continue
        cat_stories = sections_map.get(cn, [])
        if not cat_stories:
            logger.info(f"  Empty category: {cn} (rendering header)")
            md += ["", f"## {cn} (0 stories)", ""]
            continue
        md += ["", f"## {cn} ({len(cat_stories)} stories)", ""]
        for idx, st in enumerate(cat_stories):
            title_text = st["title"]
            url_val = st["link"]
            link_md = (
                f"[{title_text}]({url_val})"
                if url_val and url_val != "#"
                else title_text
            )
            pub_line = (
                f"\n*Originally published on:* {st['pub_date']}"
                if st.get("pub_date")
                else ""
            )
            tags_md = ""
            if "title" in st and st["title"]:
                tags_md = tag_story_with_keywords(st["title"], cn)
            md.append("")
            md.append(f"{idx + 1}. {link_md}")
            md.append(st["summary"] + pub_line)
            md.append(tags_md)

        md.append("---")

    return md


def write_report(filepath, md):
    """Write md string list to file.

    Args:
        filepath: output file path
        md: list of md strings
    """
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    logger.info(f"File written to {filepath}")
