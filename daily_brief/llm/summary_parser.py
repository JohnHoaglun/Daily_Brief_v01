"""
Daily Brief — Batch summary parsing.

Extracts summaries from flexible LLM batch outputs (STORY_N, numbered headings, etc.).
"""

import asyncio
import difflib
import logging
import re

from daily_brief.utils import _safe_sentence_summary

logger = logging.getLogger(__name__)

def parse_batch_summary_response(response, count, story_headlines=None):
    """
    Parse summaries from flexible batch output formats:
      ### 1. ..., 1. ..., 1) ..., STORY_0 ...
      STORY_N | <headline excerpt>=<summary>
    Returns list of length count.

    If story_headlines is provided (list of title strings), uses headline keyword
    overlap to match summaries to the correct stories, tolerating out-of-order output.
    """
    results = ["" for _ in range(count)]
    if not response:
        return results

    lines = response.splitlines()

    # Extract STORY_N | <text> blocks (may or may not have = separator)
    story_line_re = re.compile(r"STORY[_\-\s]*(\d+)\s*\|?\s*(.*)$", flags=re.IGNORECASE)

    # Track which indices were matched by headline
    matched_by_headline = set()
    matched_by_summary_overlap = set()
    # Track story indices that fuzzy-matched a headline but were skipped (duplicates)
    skipped_fuzzy_match = set()
    # Slots that should remain empty because a duplicate consumed that position
    reserved_empty_slots = set()

    if story_headlines:
        processed_story_lines = set()
        for line_idx, line in enumerate(lines):
            m = story_line_re.match(line.strip())
            if not m:
                continue
            processed_story_lines.add(line_idx)

            idx = int(m.group(1))
            rest_text = m.group(2).strip()

            if not rest_text:
                continue

            # Try to split at '=' first
            summary_text = rest_text
            if "=" in rest_text:
                eq_parts = rest_text.split("=", 1)
                summary_text = eq_parts[1].strip() if len(eq_parts) > 1 else rest_text

            # Clean summary: remove leading STORY_N numbers if present
            summary_text = re.sub(r"^STORY[_\-\s]*\d+\s*\|?\s*", "", summary_text).strip()

            if not summary_text:
                continue

            # Strategy 0: Fuzzy headline matching via difflib SequenceMatcher
            # Compare the headline excerpt (before '=') against input headlines.
            # Catches cases where keyword overlap fails due to LLM paraphrasing.
            def _normalize(text):
                return re.sub(r"\s+", " ", text.strip().lower())

            # Extract the headline excerpt portion (before '=' if present)
            headline_excerpt = rest_text.split("=", 1)[0].strip()

            best_fuzzy_idx = None
            best_fuzzy_score = 0.0
            if headline_excerpt:
                excerpt_normalized = _normalize(headline_excerpt)
                for si, sh in enumerate(story_headlines):
                    sh_normalized = _normalize(sh)
                    ratio = difflib.SequenceMatcher(
                        None, excerpt_normalized, sh_normalized
                    ).ratio()
                    if ratio > best_fuzzy_score:
                        best_fuzzy_score = ratio
                        best_fuzzy_idx = si

            fuzzy_threshold = 0.7
            if (
                headline_excerpt
                and best_fuzzy_idx is not None
                and best_fuzzy_score >= fuzzy_threshold
                and best_fuzzy_idx < count
            ):
                if best_fuzzy_idx in matched_by_headline:
                    logger.debug(
                        f"Parsed STORY_{idx} -> fuzzy match headline[{best_fuzzy_idx}] score {best_fuzzy_score:.2f} — ALREADY ASSIGNED, skipping"
                    )
                    skipped_fuzzy_match.add(idx)
                    if 0 <= idx < count:
                        reserved_empty_slots.add(idx)
                    continue
                cleaned_summary = _safe_sentence_summary(summary_text)
                if best_fuzzy_idx in reserved_empty_slots and 0 <= idx < count:
                    assign_fuzzy = idx
                else:
                    assign_fuzzy = best_fuzzy_idx
                if cleaned_summary:
                    results[assign_fuzzy] = cleaned_summary
                    matched_by_headline.add(assign_fuzzy)
                logger.debug(
                    f"Parsed STORY_{idx} -> fuzzy match headline[{best_fuzzy_idx}] score {best_fuzzy_score:.2f}"
                )
                continue

            # Strategy 1: Match by summary-to-headline keyword overlap
            # Find the best matching story by checking keyword overlap between
            # the summary text and each headline
            best_idx = None
            best_score = 0.0

            # Extract significant words from summary (first 20 words only)
            summary_words = set(re.findall(r"\b[a-z]{4,}\b", summary_text[:150].lower()))

            for si, sh in enumerate(story_headlines):
                sh_words = set(re.findall(r"\b[a-z]{4,}\b", sh.lower()))
                if not sh_words or not summary_words:
                    continue
                # Overlap: how many headline words appear in the summary
                overlap = len(sh_words & summary_words) / len(sh_words)
                if overlap > best_score:
                    best_score = overlap
                    best_idx = si

            # If >= 30% of headline words appear in summary, it's a match
            if best_idx is not None and best_score >= 0.3 and best_idx < count:
                if best_idx in matched_by_headline:
                    logger.debug(
                        f"Parsed STORY_{idx} -> matched headline[{best_idx}] overlap {best_score:.2f} — ALREADY ASSIGNED, skipping"
                    )
                    skipped_fuzzy_match.add(idx)
                    if 0 <= idx < count:
                        reserved_empty_slots.add(idx)
                    continue
                # Redirect from reserved-empty slots to positional index
                if best_idx in reserved_empty_slots:
                    assign_idx = idx if 0 <= idx < count else best_idx
                else:
                    assign_idx = best_idx
                cleaned_summary = _safe_sentence_summary(summary_text)
                if cleaned_summary:
                    results[assign_idx] = cleaned_summary
                    matched_by_headline.add(assign_idx)
                logger.debug(
                    f"Parsed STORY_{idx} -> matched headline[{best_idx}] 'overlap {best_score:.2f}'"
                )
                continue

            # Strategy 2: If LLM includes headline excerpt, match by headline
            # Split rest_text: first ~4-8 words are the headline excerpt, rest is summary
            parts = rest_text.split()
            if len(parts) > 8:
                # Try first 4-10 words as headline excerpt
                for excerpt_len in range(4, min(11, len(parts))):
                    headline_excerpt = " ".join(parts[:excerpt_len]).lower()
                    excerpt_words = set(re.findall(r"\b[a-z]{4,}\b", headline_excerpt))

                    if not excerpt_words:
                        continue

                    best_idx2 = None
                    best_score2 = 0.0
                    for si, sh in enumerate(story_headlines):
                        sh_words = set(re.findall(r"\b[a-z]{4,}\b", sh.lower()))
                        if not sh_words:
                            continue
                        overlap = len(sh_words & excerpt_words) / len(excerpt_words)
                        if overlap > best_score2:
                            best_score2 = overlap
                            best_idx2 = si

                    if best_idx2 is not None and best_score2 >= 0.3 and best_idx2 < count:
                        summary_part = " ".join(parts[excerpt_len:])
                        cleaned_summary = _safe_sentence_summary(summary_part)
                        if best_idx2 in matched_by_headline:
                            skipped_fuzzy_match.add(idx)
                            if 0 <= idx < count:
                                reserved_empty_slots.add(idx)
                        elif cleaned_summary:
                            assign_idx2 = (
                                idx
                                if (best_idx2 in reserved_empty_slots and 0 <= idx < count)
                                else best_idx2
                            )
                            results[assign_idx2] = cleaned_summary
                            matched_by_headline.add(assign_idx2)
                        logger.debug(
                            f"Parsed STORY_{idx} -> matched headline[{best_idx2}] 'excerpt overlap {best_score2:.2f}'"
                        )
                        break

    # Log unmatched stories — warn when positional fallback is needed
    matched_count = len(matched_by_headline)
    unmatched = [i for i in range(count) if i not in matched_by_headline]
    if not matched_count:
        logger.warning(
            f"[MATCH] 0/{count} by fuzzy/keyword — SKIPPING positional fallback, all slots remain empty"
        )
    elif unmatched:
        logger.warning(
            f"[MATCH] {matched_count}/{count} by fuzzy/keyword, {len(unmatched)} stories falling back to positional index"
        )
    else:
        logger.debug(f"[MATCH] {matched_count}/{count} by fuzzy/keyword — all resolved")

    if not story_headlines:
        processed_story_lines = set()
    if story_headlines and not matched_count and processed_story_lines:
        return results

    # Fallback: original index-based positional parsing for unmatched stories
    heading_re = re.compile(
        r"^\s*(?:###\s*)?(?:\*\*)?(?:(\d+)[\)\.]\s*|STORY[_\-\s]*(\d+)\s*[:\)]?\s*)(.*)$",
        flags=re.IGNORECASE,
    )

    headers = []
    story_key_re = re.compile(r"STORY[_\-\s]*(\d+)", flags=re.IGNORECASE)

    for i, line in enumerate(lines):
        m = heading_re.match(line.strip())
        if m:
            idx = m.group(1) or m.group(2)
            if not idx:
                continue
            idx = int(idx)
            if m.group(1) is not None and idx > 0:
                idx -= 1
            if 0 <= idx < count:
                headers.append((i, idx, line))

            m2 = story_key_re.match(line.strip())
            if m2 and m2.group(1):
                idx = int(m2.group(1))
                if idx > 0:
                    idx -= 1
                if 0 <= idx < count:
                    if (i, idx, line) not in headers:
                        headers.append((i, idx, line))

    # If the model used a 'Summary of ...:' style heading, capture those too.
    if not headers:
        for i, line in enumerate(lines):
            l = line.lower()
            if l.startswith("summary") and ":" in line and count > 1:
                headers.append((i, None, line))

    if not headers:
        # If the model returned a single plain paragraph for one story, use it as fallback.
        if count == 1:
            cleaned = "\n".join(
                [
                    l
                    for l in lines
                    if l.strip()
                    and not l.strip().startswith("Here are")
                    and not l.strip().startswith("***")
                ]
            ).strip()
            if cleaned:
                results[0] = _safe_sentence_summary(cleaned)
        return results

    # Normalize duplicate headers and assign missing indexes in sequence.
    normalized = []
    for line_idx, idx, raw in headers:
        if idx is None:
            normalized.append((line_idx, None, raw))
        else:
            normalized.append((line_idx, idx, raw))
    headers = normalized
    if count > 1 and all(h[1] is None for h in headers):
        # No explicit index markers; distribute chunks sequentially across lines.
        fallback_chunks = []
        current = []
        for i, line in enumerate(lines):
            if line.strip().lower().startswith("summary of") and i > 0:
                if current:
                    fallback_chunks.append(current)
                    current = []
            current.append(line)
        if current:
            fallback_chunks.append(current)
        for i, chunk in enumerate(fallback_chunks[:count]):
            results[i] = _safe_sentence_summary("\n".join(chunk).strip())
        return results

    for n, (line_idx, idx, raw) in enumerate(headers):
        # Skip lines already processed as STORY_N blocks
        if story_headlines and line_idx in processed_story_lines:
            continue
        # Skip stories that fuzzy-matched a headline but were skipped (duplicates)
        if story_headlines and idx in skipped_fuzzy_match:
            continue

        # Fuzzy headline matching in positional fallback
        # Try to match the heading text to story headlines, preventing
        # wrong summary assignment when LLM reorders output
        fuzzy_idx = idx
        fuzzy_score = 0.0
        if story_headlines:
            _norm = lambda t: re.sub(r"\s+", " ", str(t).strip().lower())
            _sig = lambda t: set(re.findall(r"\b[a-z]{4,}\b", _norm(t)))
            raw_clean = _norm(re.sub(r"^(#{2,3}\s*)?\*{0,2}\d+[\)\.]\s*", "", raw))
            best_si = None
            best_s = 0.0
            for si, sh in enumerate(story_headlines):
                s = _sig(raw_clean) & _sig(sh)
                ratio = len(s) / max(len(_sig(sh)), 1)
                if ratio > best_s:
                    best_s = ratio
                    best_si = si
            # Also try difflib ratio on full text
            if best_s < 0.7:
                rn = _norm(raw_clean)
                for si, sh in enumerate(story_headlines):
                    sn = _norm(sh)
                    r = difflib.SequenceMatcher(None, rn, sn).ratio()
                    if r > best_s:
                        best_s = r
                        best_si = si
            if best_si is not None and best_s >= 0.15:
                fuzzy_idx = best_si
                fuzzy_score = best_s

        # If fuzzy target already matched by STORY_N block, use positional idx
        if fuzzy_idx != idx and fuzzy_idx in matched_by_headline:
            fuzzy_idx = idx

        start = line_idx
        end = len(lines)
        if n + 1 < len(headers):
            end = headers[n + 1][0]

        chunk = "\n".join(lines[start:end]).strip()
        if not chunk:
            continue
        chunk_lines = [l for l in lines[start:end] if l.strip()]

        head = raw.strip()
        summary = head
        for sep in (":", "-", ")"):
            _, sep_token, rest = head.partition(sep)
            if sep_token:
                summary = rest.strip()
                break
        # If heading was followed by summary text on later lines (most common case), prefer that.
        if len(chunk_lines) > 1:
            summary = "\n".join(chunk_lines[1:]).strip()
        elif not summary and "." in head:
            summary = head.split(".", 1)[1].strip()
        if not summary:
            summary = "\n".join(chunk_lines).strip()

        summary = re.sub(r"^\*+\s*", "", summary)
        summary = re.sub(r"^(###\s*)?\**\d+[\)\.]\s*", "", summary)
        summary = re.sub(r"^Summary:\s*", "", summary, flags=re.IGNORECASE)
        summary = re.sub(r"\*\*|\*{2,}$", "", summary).strip()
        target_idx = fuzzy_idx if fuzzy_idx != idx else idx
        if target_idx in matched_by_headline:
            continue
        if target_idx in reserved_empty_slots:
            continue
        results[target_idx] = _safe_sentence_summary(summary)
        if fuzzy_idx != idx:
            matched_by_headline.add(target_idx)
            logger.debug(
                f"[MATCH] Pos idx {idx} -> fuzzy headline idx {target_idx} (score {fuzzy_score:.2f})"
            )

    # Post-match: detect and fix adjacent swap pairs
    # If two adjacent stories' summaries are each a better match for the OTHER
    # headline, swap them to fix off-by-one misalignment
    if story_headlines:
        for i in range(len(results) - 1):
            j = i + 1
            hi = story_headlines[i] if i < len(story_headlines) else ""
            hj = story_headlines[j] if j < len(story_headlines) else ""
            si = results[i].lower()
            sj = results[j].lower()
            if not si or not sj or not hi or not hj:
                continue
            hi_words = set(re.findall(r"\b[a-z]{3,}\b", hi.lower()))
            hj_words = set(re.findall(r"\b[a-z]{3,}\b", hj.lower()))
            if not hi_words or not hj_words:
                continue
            overlap_i_to_j = len(hj_words & set(re.findall(r"\b[a-z]{3,}\b", si))) / len(hj_words)
            overlap_j_to_i = len(hi_words & set(re.findall(r"\b[a-z]{3,}\b", sj))) / len(hi_words)
            overlap_i_normal = len(hi_words & set(re.findall(r"\b[a-z]{3,}\b", si))) / len(
                hi_words
            )
            overlap_j_normal = len(hj_words & set(re.findall(r"\b[a-z]{3,}\b", sj))) / len(
                hj_words
            )
            if overlap_i_to_j > overlap_i_normal and overlap_j_to_i > overlap_j_normal:
                results[i], results[j] = results[j], results[i]
                logger.debug(
                    f"SWAP FIX: swapped stories {i} and {j} (cross-overlap {overlap_i_to_j:.2f}/{overlap_j_to_i:.2f} > normal {overlap_i_normal:.2f}/{overlap_j_normal:.2f})"
                )

        # All-pairs keyword overlap validation: detect non-adjacent swaps (3+ story shift)
        for i in range(len(results)):
            if i >= len(story_headlines):
                continue
            headline = story_headlines[i]
            summary = results[i]
            if not headline or not summary:
                continue
            hl_words = set(re.findall(r"\b[a-z]{3,}\b", headline.lower()))
            sum_words = set(re.findall(r"\b[a-z]{3,}\b", summary.lower()))
            if not hl_words:
                continue
            overlap_pct = len(hl_words & sum_words) / len(hl_words)
            if overlap_pct < 0.2:
                # Find which story's headline this summary matches best
                best_mismatch_idx = None
                best_mismatch_score = 0.0
                for m in range(len(story_headlines)):
                    if m == i:
                        continue
                    mh_words = set(re.findall(r"\b[a-z]{3,}\b", story_headlines[m].lower()))
                    if not mh_words:
                        continue
                    m_score = len(mh_words & sum_words) / len(mh_words)
                    if m_score > best_mismatch_score:
                        best_mismatch_score = m_score
                        best_mismatch_idx = m
                if best_mismatch_idx is not None:
                    logger.warning(
                        f'[SWAP DETECTED] Story {i} (headline "{headline}") assigned summary from story '
                        f"{best_mismatch_idx} — keyword overlap {overlap_pct * 100:.0f}%"
                    )
                else:
                    logger.warning(
                        f'[SWAP DETECTED] Story {i} (headline "{headline}") — topic mismatch, '
                        f"keyword overlap {overlap_pct * 100:.0f}%"
                    )

    return results
