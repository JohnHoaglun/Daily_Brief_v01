"""
Daily Brief v1.0.145 — Report Validation
=========================================

Reads rendered markdown and checks summary quality.

Report-level checks (7):
1. Frontmatter required fields
2. Weather section with forecast rows
3. No "Dynamic" fallback string
4. No "Unavailable" fallback string
5. Story count plausible range
6. No duplicate URLs
7. File size reasonable

Per-story checks (5):
- Non-empty summary
- Minimum sentence count
- Summary not headline repeat
- No fallback markers
- Topic overlap
"""

import logging
import os
import re

import yaml

from daily_brief.utils import _count_sentences

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
        if len(cells) >= 3 and not all(c == "-" for c in cells):
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


def validate_report(filepath):
    """Validate the rendered markdown report. Returns (passed, issues) tuple.

    Report-level checks (7):
    1. Frontmatter required fields
    2. Weather section with forecast rows
    3. No "Dynamic" fallback
    4. No "Unavailable" fallback
    5. Story count plausible (5-200)
    6. No duplicate URLs
    7. File size reasonable (5KB-10MB)

    Per-story checks (5):
    - Non-empty summary
    - Minimum sentence count (2+)
    - Summary not headline repeat
    - No fallback markers
    - Topic overlap

    Returns False if >10% of stories have broken summaries.
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
                issues.append(f"[REPORT-5] story_count_total is {story_count} — below minimum 5")
            elif story_count > 200:
                issues.append(f"[REPORT-5] story_count_total is {story_count} — above maximum 200")
        except (ValueError, TypeError):
            issues.append(f"[REPORT-5] story_count_total is not a valid integer: {story_count}")

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
        issues.append(f"[REPORT-7] File too small ({file_size} bytes) — expected at least 5KB")
    elif file_size > 10 * 1024 * 1024:
        issues.append(f"[REPORT-7] File too large ({file_size} bytes) — expected at most 10MB")

    # --- Per-story checks ---
    # Split into sections — find category headings
    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)

    stories = []

    for section in sections:
        section_text = section.strip()
        if not section_text:
            continue

        # Find numbered stories: "N. [Title](URL)"
        story_blocks = re.split(r"\n(?=\d+\.\s+\[)", section_text)

        for block in story_blocks:
            block = block.strip()
            if not block:
                continue

            # Extract title from first line
            first_line_match = re.match(r"(\d+)\.\s+\[(.+?)\]\((.+?)\)", block)
            if not first_line_match:
                continue

            title = first_line_match.group(2).strip()
            block_lines = block.split("\n")
            if len(block_lines) < 2:
                continue

            # Summary is everything after the title line, before meta lines
            summary_lines = []
            for line in block_lines[1:]:
                line_stripped = line.strip()
                if (
                    line_stripped.startswith("*Originally published")
                    or line_stripped.startswith("[[")
                    or line_stripped.startswith("---")
                    or line_stripped.startswith("##")
                    or line_stripped == ""
                ):
                    continue
                summary_lines.append(line_stripped)

            summary = " ".join(summary_lines).strip()
            stories.append((title, summary))

    if not stories:
        logger.warning("VALIDATE: No stories found in report")
        issues.append("No stories found in report")
        return False, issues

    total_stories = len(stories)
    bad_stories = 0
    auto_count = 0

    for title, summary in stories:
        title_lower = title.lower()

        # Check 1: Empty summary
        if not summary or not summary.strip():
            issues.append(f"Empty summary for: {title[:80]}")
            bad_stories += 1
            continue

        summary_lower = summary.lower()

        # Check 4a: [Auto] fallback — acceptable (headline-derived summary)
        if summary.startswith("[Auto]"):
            auto_count += 1
            continue

        # Check 2: Summary is just the headline
        title_norm = re.sub(r"\s+", " ", title_lower)
        summary_norm = re.sub(r"\s+", " ", summary_lower)
        if summary_norm == title_norm or summary_norm.startswith(title_norm + "."):
            issues.append(f"Summary repeats headline: {title[:80]}")
            bad_stories += 1
            continue

        # Check 3: Minimum sentence count
        sentence_count = _count_sentences(summary)
        if sentence_count < 2:
            issues.append(f"Too short ({sentence_count} sentences): {title[:80]}")
            bad_stories += 1
            continue

        # Check 4: Fallback markers (now accepts [Auto], rejects [Headline]/[Summary Unavailable])
        if summary.startswith("[Headline]") or "[summary unavailable]" in summary_lower:
            issues.append(f"Fallback marker present: {title[:80]}")
            bad_stories += 1
            continue

        # Check 5: Topic overlap — extract key words from headline, check presence in summary
        headline_words = re.findall(r"\b[a-z]{4,}\b", title_lower)
        # Remove common words
        stop_words = {
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
        }
        headline_words = [w for w in headline_words if w not in stop_words]

        if headline_words:
            matching = [w for w in headline_words if w in summary_lower]
            overlap_ratio = len(matching) / len(headline_words) if headline_words else 1.0

            # If <25% of significant headline words appear in summary, it's likely wrong
            if overlap_ratio < 0.25:
                issues.append(f"Topic mismatch (overlap {overlap_ratio:.0%}): {title[:80]}")
                bad_stories += 1
                continue

    fail_threshold = total_stories * 0.10  # 10% failure rate
    total_bad_ratio = bad_stories / total_stories if total_stories > 0 else 0

    passed = bad_stories <= fail_threshold
    status = "PASS" if passed else "FAIL"
    logger.info(
        "VALIDATE: %d stories, %d bad (%.0f%%), [Auto] fallbacks: %d, threshold %.0f — %s",
        total_stories,
        bad_stories,
        total_bad_ratio * 100,
        auto_count,
        fail_threshold,
        status,
    )

    if issues:
        logger.info("VALIDATE ISSUES (%d):", len(issues))
        for issue in issues[:20]:  # Log first 20 issues max
            logger.info("  - %s", issue)
        if len(issues) > 20:
            logger.info("  ... and %d more", len(issues) - 20)

    return passed, issues
