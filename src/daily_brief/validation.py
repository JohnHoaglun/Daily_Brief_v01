"""
Daily Brief v1.0.13 — Report Validation
=========================================

Reads rendered markdown and checks summary quality.
"""

import logging
import re

from daily_brief.llm.summarizer import _count_sentences

logger = logging.getLogger(__name__)


def validate_report(filepath):
    """Validate the rendered markdown report. Returns (passed, issues) tuple.

    Checks each story for:
    - Non-empty summary
    - Minimum sentence count (2 sentences or more)
    - Summary is not just the headline repeated
    - Headline/summary topic overlap (keyword matching)

    Returns False if >10% of stories have broken summaries.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            content = fh.read()
    except Exception as e:
        logger.error("VALIDATE ERROR: Cannot read %s: %s", filepath, e)
        return False, [f"Cannot read file: {e}"]

    # Split into sections — find category headings
    sections = re.split(r'^##\s+', content, flags=re.MULTILINE)

    stories = []
    issues = []

    for section in sections:
        section_text = section.strip()
        if not section_text:
            continue

        # Find numbered stories: "N. [Title](URL)"
        story_blocks = re.split(r'\n(?=\d+\.\s+\[)', section_text)

        for block in story_blocks:
            block = block.strip()
            if not block:
                continue

            # Extract title from first line
            first_line_match = re.match(r'(\d+)\.\s+\[(.+?)\]\((.+?)\)', block)
            if not first_line_match:
                continue

            title = first_line_match.group(2).strip()
            block_lines = block.split('\n')
            if len(block_lines) < 2:
                continue

            # Summary is everything after the title line, before meta lines
            summary_lines = []
            for line in block_lines[1:]:
                line_stripped = line.strip()
                if line_stripped.startswith('*Originally published') or \
                   line_stripped.startswith('[[') or \
                   line_stripped.startswith('---') or \
                   line_stripped.startswith('##') or \
                   line_stripped == '':
                    continue
                summary_lines.append(line_stripped)

            summary = ' '.join(summary_lines).strip()
            stories.append((title, summary))

    if not stories:
        logger.warning("VALIDATE: No stories found in report")
        return False, ["No stories found in report"]

    total_stories = len(stories)
    bad_stories = 0

    for title, summary in stories:
        title_lower = title.lower()

        # Check 1: Empty summary
        if not summary or not summary.strip():
            issues.append(f"Empty summary for: {title[:80]}")
            bad_stories += 1
            continue

        summary_lower = summary.lower()

        # Check 2: Summary is just the headline
        title_norm = re.sub(r'\s+', ' ', title_lower)
        summary_norm = re.sub(r'\s+', ' ', summary_lower)
        if summary_norm == title_norm or summary_norm.startswith(title_norm + '.'):
            issues.append(f"Summary repeats headline: {title[:80]}")
            bad_stories += 1
            continue

        # Check 3: Minimum sentence count
        sentence_count = _count_sentences(summary)
        if sentence_count < 2:
            issues.append(f"Too short ({sentence_count} sentences): {title[:80]}")
            bad_stories += 1
            continue

        # Check 4: Fallback markers
        if summary.startswith("[Headline]") or "[unavailable" in summary_lower:
            issues.append(f"Fallback marker present: {title[:80]}")
            bad_stories += 1
            continue

        # Check 5: Topic overlap — extract key words from headline, check presence in summary
        headline_words = re.findall(r'\b[a-z]{4,}\b', title_lower)
        # Remove common words
        stop_words = {'news', 'says', 'live', 'update', 'updates', 'here', 'what', 'how', 'why', 'when', 'year', 'report', 'story', 'today'}
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
        "VALIDATE: %d stories, %d bad (%.0f%%), threshold %.0f — %s",
        total_stories, bad_stories, total_bad_ratio * 100, fail_threshold, status,
    )

    if issues:
        logger.info("VALIDATE ISSUES (%d):", len(issues))
        for issue in issues[:20]:  # Log first 20 issues max
            logger.info("  - %s", issue)
        if len(issues) > 20:
            logger.info("  ... and %d more", len(issues) - 20)

    return passed, issues
