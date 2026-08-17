"""
Daily Brief — Report Validation
=========================================

Semantic validation of Story objects (Phase 3D) and final-artifact format
validation (Phase 5).

Phase 3D — validate_stories(stories):
    Validates canonical Story objects immediately after summarization.
    Checks: empty summary, [Auto] exemption, headline repetition,
    sentence count, fallback markers, topic overlap.

Phase 5 — validate_report(filepath):
    Validates the rendered markdown file. Checks: frontmatter, weather section,
    fallback values in body, plausible story count, duplicate URLs, file size.
    Does NOT re-parse story blocks (those are validated in Phase 3D).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, List, Sequence, Tuple

import yaml

from daily_brief.models import Story
from daily_brief.utils import _count_sentences, extract_significant_words

logger = logging.getLogger(__name__)


def _parse_frontmatter(content):
    """Parse YAML frontmatter between --- delimiters. Returns (metadata_dict, body)."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    yamls = parts[1].strip()
    body = parts[2].strip()
    try:
        metadata = yaml.safe_load(yamls) or {}
    except Exception:
        metadata = {}
    return metadata, body


def _count_forecast_rows(section_text):
    """Count forecast table rows (lines with | that look like table rows, not separators)."""
    rows = 0
    for line in section_text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|") if c.strip()]
        if len(cells) >= 3 and not all(c.strip("-") == "" for c in cells):
            # Only count rows with actual forecast data (contain numeric temps)
            if any(re.search(r"\d", c) for c in cells):
                rows += 1
    return rows


def _find_weather_section(body):
    """Find the weather section in body. Returns the section content or None."""
    sections = re.split(r"^##\s+", body, flags=re.MULTILINE)
    for section in sections:
        first_line = section.strip().split("\n")[0].lower() if section.strip() else ""
        if "weather" in first_line or "forecast" in first_line:
            return section.strip()
    return None


def _extract_urls(body):
    """Extract all markdown link URLs from body text. Returns list of (title, url) tuples."""
    return re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", body)

# Stop word list for topic-overlap check.
_STOP_WORDS = frozenset({
    "news",
    "says",
    "live",
    "update",
    "updates",
    "here",
    "what",
    "how",
    "why",
    "when",
    "year",
    "report",
    "story",
    "today",
})


def validate_stories(
    stories: Sequence[Story],
) -> Tuple[bool, List[str]]:
    """Validate in-memory Story objects immediately after summarization.

    Returns ``(passed, issues)``.   *passed* is ``True`` when no more than
    10 % of stories are invalid, or when every story carries an ``[Auto]``
    fallback.  An empty collection fails unconditionally.

    Per-story validation rules (all blocking):
    1. *Empty / whitespace-only* summary → invalid.
    2. ``[Auto] …`` → exempt from all later checks.
    3. Summary is an exact headline echo (with or without trailing ``.``) → invalid.
    4. Fewer than two sentences → invalid.
    5. Starts with ``[Headline]`` or contains ``[summary unavailable]`` → invalid.
    6. Topic overlap — fewer significant headline words appear in the summary
       than the 25 % threshold → invalid.
    """
    issues: List[str] = []

    if not stories:
        issues.append("Empty story collection")
        return False, issues

    total_stories = len(stories)
    bad_stories = 0
    auto_count = 0

    for story in stories:
        title = story.title or ""
        summary = story.summary or ""
        summary_lower = summary.lower()
        title_lower = title.lower()

        # Empty summary
        if not summary or not summary.strip():
            issues.append(f"Empty summary for: {title[:80]}")
            bad_stories += 1
            continue

        # [Auto] exemption
        if summary.startswith("[Auto]"):
            auto_count += 1
            continue

        # Headline echo (with optional trailing period)
        title_norm = re.sub(r"\s+", " ", title_lower).strip()
        summary_norm = re.sub(r"\s+", " ", summary_lower).strip()
        if summary_norm == title_norm or summary_norm.startswith(title_norm + "."):
            issues.append(f"Summary repeats headline: {title[:80]}")
            bad_stories += 1
            continue

        # Minimum sentence count
        sentence_count = _count_sentences(summary)
        if sentence_count < 2:
            issues.append(f"Too short ({sentence_count} sentences): {title[:80]}")
            bad_stories += 1
            continue

        # Fallback markers
        if summary.startswith("[Headline]") or "[summary unavailable]" in summary_lower:
            issues.append(f"Fallback marker present: {title[:80]}")
            bad_stories += 1
            continue

        # Topic overlap
        headline_words = extract_significant_words(title, min_len=4)
        headline_words_filtered = [w for w in headline_words if w not in _STOP_WORDS]

        if headline_words_filtered:
            matching = [w for w in headline_words_filtered if w in summary_lower]
            overlap_ratio = len(matching) / len(headline_words_filtered)

            if overlap_ratio < 0.25:
                issues.append(
                    f"Topic mismatch (overlap {overlap_ratio:.0%}): {title[:80]}"
                )
                bad_stories += 1
                continue

    fail_threshold = total_stories * 0.10
    passed = bad_stories <= fail_threshold
    status = "PASS" if passed else "FAIL"
    logger.info(
        "VALIDATE_STORIES: %d stories, %d bad (%.0f%%), [Auto] fallbacks: %d, "
        "threshold %.0f — %s",
        total_stories,
        bad_stories,
        (bad_stories / total_stories * 100) if total_stories else 0,
        auto_count,
        fail_threshold,
        status,
    )

    if issues:
        logger.info("VALIDATE_STORIES ISSUES (%d):", len(issues))
        for issue in issues[:20]:
            logger.info("  - %s", issue)
        if len(issues) > 20:
            logger.info("  ... and %d more", len(issues) - 20)

    return passed, issues


def validate_report(filepath):
    """Validate the final rendered markdown artifact (Phase 5).

    Report-level checks only — story quality is validated in Phase 3D via
    ``validate_stories(stories)`` against canonical Story objects.

    Report-level checks (7):
    1. Frontmatter required fields
    2. Weather section with forecast rows
    3. No "Dynamic" fallback string in body
    4. No "Unavailable" fallback string in body
    5. Story count plausible range
    6. No duplicate URLs
    7. File size reasonable (5 KB — 10 MB)

    Returns False if any report-level check fails.
    """
    issues = []

    try:
        file_size = os.path.getsize(filepath)
    except Exception as e:
        logger.error("VALIDATE ERROR: Cannot access %s: %s", filepath, e)
        return False, [f"Cannot access file: {e}"]

    try:
        with open(filepath, encoding="utf-8") as fh:
            content = fh.read()
    except Exception as e:
        logger.error("VALIDATE ERROR: Cannot read %s: %s", filepath, e)
        return False, [f"Cannot read file: {e}"]

    # Parse frontmatter
    metadata, body = _parse_frontmatter(content)

    # REPORT CHECK 1: Frontmatter required fields
    required_fields = [
        "title",
        "date",
        "time_generated",
        "story_count_total",
        "categories",
        "tags",
    ]
    for field in required_fields:
        if field not in metadata or metadata[field] is None:
            issues.append(f"[REPORT-1] Missing frontmatter field: {field}")

    # REPORT CHECK 2: Weather section with >=3 forecast rows
    weather_section = _find_weather_section(body)
    if not weather_section:
        issues.append("[REPORT-2] No weather section found")
    else:
        forecast_rows = _count_forecast_rows(weather_section)
        if forecast_rows < 3:
            issues.append(
                f"[REPORT-2] Weather section has only {forecast_rows} forecast rows (minimum 3)"
            )

    # REPORT CHECK 3: No "Dynamic" string in body
    if "Dynamic" in body:
        issues.append("[REPORT-3] Weather fallback 'Dynamic' found in report body")

    # REPORT CHECK 4: No "Unavailable" string in body
    if "Unavailable" in body:
        issues.append("[REPORT-4] Data fallback 'Unavailable' found in report body")

    # REPORT CHECK 5: Story count plausible
    story_count = metadata.get("story_count_total")
    if story_count is not None:
        try:
            story_count = int(story_count)
            if story_count == 0:
                issues.append("[REPORT-5] story_count_total is 0 — expected 5-200")
            elif story_count < 5:
                issues.append(
                    f"[REPORT-5] story_count_total is {story_count} — below minimum 5"
                )
            elif story_count > 200:
                issues.append(
                    f"[REPORT-5] story_count_total is {story_count} — above maximum 200"
                )
        except (ValueError, TypeError):
            issues.append(
                f"[REPORT-5] story_count_total is not a valid integer: {story_count}"
            )

    # REPORT CHECK 6: No duplicate URLs
    urls = _extract_urls(body)
    url_list = [url for _, url in urls]
    seen = {}
    for u in url_list:
        seen[u] = seen.get(u, 0) + 1
    dupes = {u: c for u, c in seen.items() if c > 1}
    if dupes:
        dup_count = len(dupes)
        issues.append(f"[REPORT-6] Found {dup_count} duplicate URL(s) in report")

    # REPORT CHECK 7: File size reasonable
    if file_size < 5 * 1024:
        issues.append(
            f"[REPORT-7] File too small ({file_size} bytes) — expected at least 5KB"
        )
    elif file_size > 10 * 1024 * 1024:
        issues.append(
            f"[REPORT-7] File too large ({file_size} bytes) — expected at most 10MB"
        )

    passed = not issues
    status = "PASS" if passed else "FAIL"
    logger.info("VALIDATE_REPORT: %s — %d issues", status, len(issues))

    if issues:
        logger.info("VALIDATE_REPORT ISSUES (%d):", len(issues))
        for issue in issues:
            logger.info("  - %s", issue)

    return passed, issues
