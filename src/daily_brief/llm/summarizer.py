import asyncio
import difflib
import logging
import re
import time
from daily_brief.utils import (
    _safe_text,
    _safe_sentence_summary,
    _count_sentences,
    build_context,
)
from daily_brief.config import (
    LLM_MODEL,
    LLM_SUMMARY_TRIM_MIN_CHARS,
    LLM_SUMMARY_CONTEXT_CHARS,
    LLM_SUMMARY_OPTIONS,
    LLM_SUMMARY_RETRY_ATTEMPTS,
    LLM_SUMMARY_RETRY_BACKOFF,
    LLM_CONTEXT_PREVIEW_CHARS,
    SUMMARY_PROMPT,
    SUMMARY_STRICT_PROMPT,
    SYSTEM_BATCH_PROMPT,
)
from daily_brief.llm.summary_metrics import SummaryMetrics, empty_metrics

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
    story_line_re = re.compile(
        r"STORY[_\-\s]*(\d+)\s*\|?\s*(.*)$",
        flags=re.IGNORECASE
    )

    # Track which indices were matched by headline
    matched_by_headline = set()
    matched_by_summary_overlap = set()

    if story_headlines:
        for line in lines:
            m = story_line_re.match(line.strip())
            if not m:
                continue

            idx = int(m.group(1))
            rest_text = m.group(2).strip()

            if not rest_text:
                continue

            # Try to split at '=' first
            summary_text = rest_text
            if '=' in rest_text:
                eq_parts = rest_text.split('=', 1)
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
            headline_excerpt = rest_text.split('=', 1)[0].strip()

            best_fuzzy_idx = None
            best_fuzzy_score = 0.0
            if headline_excerpt:
                excerpt_normalized = _normalize(headline_excerpt)
                for si, sh in enumerate(story_headlines):
                    sh_normalized = _normalize(sh)
                    ratio = difflib.SequenceMatcher(None, excerpt_normalized, sh_normalized).ratio()
                    if ratio > best_fuzzy_score:
                        best_fuzzy_score = ratio
                        best_fuzzy_idx = si

            fuzzy_threshold = 0.7
            if headline_excerpt and best_fuzzy_idx is not None and best_fuzzy_score >= fuzzy_threshold and best_fuzzy_idx < count:
                cleaned_summary = _safe_sentence_summary(summary_text)
                if cleaned_summary:
                    results[best_fuzzy_idx] = cleaned_summary
                    matched_by_headline.add(best_fuzzy_idx)
                logger.debug(f"Parsed STORY_{idx} -> fuzzy match headline[{best_fuzzy_idx}] score {best_fuzzy_score:.2f}")
                continue

            # Strategy 1: Match by summary-to-headline keyword overlap
            # Find the best matching story by checking keyword overlap between
            # the summary text and each headline
            best_idx = None
            best_score = 0.0

            # Extract significant words from summary (first 20 words only)
            summary_words = set(re.findall(r'\b[a-z]{4,}\b', summary_text[:150].lower()))

            for si, sh in enumerate(story_headlines):
                sh_words = set(re.findall(r'\b[a-z]{4,}\b', sh.lower()))
                if not sh_words or not summary_words:
                    continue
                # Overlap: how many headline words appear in the summary
                overlap = len(sh_words & summary_words) / len(sh_words)
                if overlap > best_score:
                    best_score = overlap
                    best_idx = si

            # If >= 30% of headline words appear in summary, it's a match
            if best_idx is not None and best_score >= 0.3 and best_idx < count:
                cleaned_summary = _safe_sentence_summary(summary_text)
                if cleaned_summary:
                    results[best_idx] = cleaned_summary
                    matched_by_headline.add(best_idx)
                logger.debug(f"Parsed STORY_{idx} -> matched headline[{best_idx}] 'overlap {best_score:.2f}'")
                continue

            # Strategy 2: If LLM includes headline excerpt, match by headline
            # Split rest_text: first ~4-8 words are the headline excerpt, rest is summary
            parts = rest_text.split()
            if len(parts) > 8:
                # Try first 4-10 words as headline excerpt
                for excerpt_len in range(4, min(11, len(parts))):
                    headline_excerpt = ' '.join(parts[:excerpt_len]).lower()
                    excerpt_words = set(re.findall(r'\b[a-z]{4,}\b', headline_excerpt))

                    if not excerpt_words:
                        continue

                    best_idx2 = None
                    best_score2 = 0.0
                    for si, sh in enumerate(story_headlines):
                        sh_words = set(re.findall(r'\b[a-z]{4,}\b', sh.lower()))
                        if not sh_words:
                            continue
                        overlap = len(sh_words & excerpt_words) / len(excerpt_words)
                        if overlap > best_score2:
                            best_score2 = overlap
                            best_idx2 = si

                    if best_idx2 is not None and best_score2 >= 0.3 and best_idx2 < count:
                        summary_part = ' '.join(parts[excerpt_len:])
                        cleaned_summary = _safe_sentence_summary(summary_part)
                        if cleaned_summary and best_idx2 not in matched_by_headline:
                            results[best_idx2] = cleaned_summary
                            matched_by_headline.add(best_idx2)
                        logger.debug(f"Parsed STORY_{idx} -> matched headline[{best_idx2}] 'excerpt overlap {best_score2:.2f}'")
                        break

    # Log unmatched stories — warn when positional fallback is needed
    matched_count = len(matched_by_headline)
    unmatched = [i for i in range(count) if i not in matched_by_headline]
    if not matched_count:
        logger.warning(f"[MATCH] 0/{count} by fuzzy/keyword — falling back to positional index for ALL stories")
    elif unmatched:
        logger.warning(f"[MATCH] {matched_count}/{count} by fuzzy/keyword, {len(unmatched)} stories falling back to positional index")
    else:
        logger.debug(f"[MATCH] {matched_count}/{count} by fuzzy/keyword — all resolved")

    # Ensure matched_by_headline exists for positional fallback
    if 'matched_by_headline' not in dir():
        matched_by_headline = set()

    # Fallback: original index-based positional parsing for unmatched stories
    heading_re = re.compile(
        r"^\s*(?:###\s*)?(?:\*\*)?(?:(\d+)[\)\.]\s*|STORY[_\-\s]*(\d+)\s*[:\)]?\s*)(.*)$",
        flags=re.IGNORECASE
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
                [l for l in lines if l.strip() and not l.strip().startswith("Here are") and not l.strip().startswith("***")]
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
        # Skip if already matched by headline
        if idx in matched_by_headline:
            continue

        # Fuzzy headline matching in positional fallback
        # Try to match the heading text to story headlines, preventing
        # wrong summary assignment when LLM reorders output
        fuzzy_idx = idx
        fuzzy_score = 0.0
        if story_headlines:
            _norm = lambda t: re.sub(r"\s+", " ", str(t).strip().lower())
            _sig = lambda t: set(re.findall(r'\b[a-z]{4,}\b', _norm(t)))
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
        results[target_idx] = _safe_sentence_summary(summary)
        if fuzzy_idx != idx:
            matched_by_headline.add(target_idx)
            logger.debug(f"[MATCH] Pos idx {idx} -> fuzzy headline idx {target_idx} (score {fuzzy_score:.2f})")

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
            hi_words = set(re.findall(r'\b[a-z]{3,}\b', hi.lower()))
            hj_words = set(re.findall(r'\b[a-z]{3,}\b', hj.lower()))
            if not hi_words or not hj_words:
                continue
            overlap_i_to_j = len(hj_words & set(re.findall(r'\b[a-z]{3,}\b', si))) / len(hj_words)
            overlap_j_to_i = len(hi_words & set(re.findall(r'\b[a-z]{3,}\b', sj))) / len(hi_words)
            overlap_i_normal = len(hi_words & set(re.findall(r'\b[a-z]{3,}\b', si))) / len(hi_words)
            overlap_j_normal = len(hj_words & set(re.findall(r'\b[a-z]{3,}\b', sj))) / len(hj_words)
            if overlap_i_to_j > overlap_i_normal and overlap_j_to_i > overlap_j_normal:
                results[i], results[j] = results[j], results[i]
                logger.debug(f"SWAP FIX: swapped stories {i} and {j} (cross-overlap {overlap_i_to_j:.2f}/{overlap_j_to_i:.2f} > normal {overlap_i_normal:.2f}/{overlap_j_normal:.2f})")

        # All-pairs keyword overlap validation: detect non-adjacent swaps (3+ story shift)
        for i in range(len(results)):
            if i >= len(story_headlines):
                continue
            headline = story_headlines[i]
            summary = results[i]
            if not headline or not summary:
                continue
            hl_words = set(re.findall(r'\b[a-z]{3,}\b', headline.lower()))
            sum_words = set(re.findall(r'\b[a-z]{3,}\b', summary.lower()))
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
                    mh_words = set(re.findall(r'\b[a-z]{3,}\b', story_headlines[m].lower()))
                    if not mh_words:
                        continue
                    m_score = len(mh_words & sum_words) / len(mh_words)
                    if m_score > best_mismatch_score:
                        best_mismatch_score = m_score
                        best_mismatch_idx = m
                if best_mismatch_idx is not None:
                    logger.warning(
                        f"[SWAP DETECTED] Story {i} (headline \"{headline}\") assigned summary from story "
                        f"{best_mismatch_idx} — keyword overlap {overlap_pct * 100:.0f}%"
                    )
                else:
                    logger.warning(
                        f"[SWAP DETECTED] Story {i} (headline \"{headline}\") — topic mismatch, "
                        f"keyword overlap {overlap_pct * 100:.0f}%"
                    )

    return results


from daily_brief.models import Story

StoryPipelineState = Story


def _generate_auto_fallback(title):
    """Generate a deterministic fallback summary from the story title alone.
    Returns: [Auto] {headline} — minimal but informative."""
    if not title:
        return "[Summary Unavailable]"
    cleaned = re.sub(r"\s+", " ", str(title)).strip()
    # Remove trailing colon, question mark clusters, and common truncation markers
    cleaned = re.sub(r"[:\-\u2014]\s*$", "", cleaned).strip()
    return f"[Auto] {cleaned}"


async def _summarize(client, context, title=None, min_chars=LLM_SUMMARY_TRIM_MIN_CHARS, strict=False):
    """Async summary call with configurable retry and boilerplate detection.

    On retry: switches to strict prompt, applies exponential backoff.
    If all attempts exhausted: returns [Auto] {title} fallback (deterministic
    summary from headline). Only falls through to "[Summary Unavailable]" if
    title is also missing.

    Configured via runtime_defaults.summary_retry in config.yaml.
    """
    from daily_brief.config import LLM_SUMMARY_RETRY_ATTEMPTS, LLM_SUMMARY_RETRY_BACKOFF

    if not context or len(context.strip()) < min_chars:
        return None

    max_attempts = LLM_SUMMARY_RETRY_ATTEMPTS
    backoff_delays = LLM_SUMMARY_RETRY_BACKOFF
    prompt = SUMMARY_STRICT_PROMPT if strict else SUMMARY_PROMPT

    for attempt in range(max_attempts):
        try:
            t0 = time.monotonic()
            r = await client.chat_completions_create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": context[:LLM_SUMMARY_CONTEXT_CHARS]}
                ],
                **LLM_SUMMARY_OPTIONS
            )
            logger.debug(f"{'STRICT ' if strict else ''}SUMMARIZE: {time.monotonic() - t0:.2f}s")
            summary_text = r.choices[0].message.content or ""
            summary_text = " ".join([ln.strip() for ln in str(summary_text).splitlines() if ln.strip()])
            if not summary_text.strip():
                logger.warning(f"Empty LLM response on attempt {attempt+1}")
                is_last = attempt >= max_attempts - 1
                if not is_last:
                    delay = backoff_delays[attempt] if attempt < len(backoff_delays) else backoff_delays[-1]
                    logger.warning(f"[RETRY] attempt {attempt+1}/{max_attempts} empty response, retrying in {delay}s")
                    await asyncio.sleep(delay)
                    prompt = SUMMARY_STRICT_PROMPT
                    strict = True
                    continue
            if not strict and _is_boilerplate(summary_text):
                logger.warning(f"BOILERPLACE DETECTED in summary attempt {attempt+1}, retrying with strict prompt...")
                prompt = SUMMARY_STRICT_PROMPT
                strict = True
                continue
            return summary_text
        except Exception as e:
            is_last = attempt >= max_attempts - 1
            delay = backoff_delays[attempt] if attempt < len(backoff_delays) else backoff_delays[-1]
            if not is_last:
                logger.warning(f"[RETRY] attempt {attempt+1}/{max_attempts} failed ({e}), retrying in {delay}s")
                await asyncio.sleep(delay)
                prompt = SUMMARY_STRICT_PROMPT
                strict = True
            else:
                logger.warning(f"{'STRICT ' if strict else ''}SUMMARIZE ERROR (final): {e}")
    # Fallback: deterministic auto-summary from title
    return _generate_auto_fallback(title)



_VALID_SUMMARY_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "at", "by", "from", "is", "are", "was", "were", "be", "been",
    "this", "that", "these", "those", "as", "it", "its", "into", "after",
    "over", "amid", "than", "their", "his", "her", "has", "have", "had",
    "will", "would", "could", "should", "about", "which", "who", "what",
    "says", "said", "new", "more", "not", "also", "some", "such", "each",
}


def _significant_words(text):
    """Extract significant words (4+ chars, not stop words) from text."""
    return {w for w in re.findall(r"[a-zA-Z']+", text.lower())
            if len(w) > 3 and w not in _VALID_SUMMARY_STOPWORDS}


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


async def _summarize_sub_batch(client, cat_name, sub_batch, *, semaphore=None, batch_size=3):
    """Process one sub-batch of stories through a single LLM batch call.
    
    Args:
        client: LLM client with chat_completions_create method
        cat_name: Category name for logging
        sub_batch: List of StoryPipelineState objects
        semaphore: Optional asyncio.Semaphore for bounded concurrency
        batch_size: Unused parameter kept for API compatibility
    """
    # Build contexts for this sub-batch
    valid_count = 0
    context_lines = []
    for idx, s in enumerate(sub_batch):
        context_parts = [s.title]
        content = build_context(s, preview_chars=LLM_CONTEXT_PREVIEW_CHARS)
        if len(content) > LLM_CONTEXT_PREVIEW_CHARS:
            content = content[:LLM_CONTEXT_PREVIEW_CHARS]
        context_parts.append(content)
        entry = f"{idx + 1}. {cat_name}\n" + "\n".join(context_parts)
        context_lines.append(entry)

    batch_text = "\n---\n\n".join(context_lines)

    try:
        t0 = time.monotonic()
        if semaphore:
            async with semaphore:
                r = await client.chat_completions_create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_BATCH_PROMPT},
                        {"role": "user", "content": batch_text}
                    ],
                    **LLM_SUMMARY_OPTIONS
                )
        else:
            r = await client.chat_completions_create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_BATCH_PROMPT},
                    {"role": "user", "content": batch_text}
                ],
                **LLM_SUMMARY_OPTIONS
            )
        elapsed = time.monotonic() - t0
        sub_batch_label = f"{cat_name} (batch {len(sub_batch)})"
        logger.debug(f"BATCH SUMMARIZE ({sub_batch_label}): {elapsed:.1f}s")

        resp_text = r.choices[0].message.content if r.choices else ""
        logger.debug(f"BATCH OUTPUT ({sub_batch_label}): {resp_text[:400]}")

        parsed_summaries = parse_batch_summary_response(
            resp_text, len(sub_batch),
            story_headlines=[s.title for s in sub_batch]
        )
        for idx, s in enumerate(sub_batch):
            summary = parsed_summaries[idx] if idx < len(parsed_summaries) else ""
            headline = s.title.strip()
            if not summary or not summary.strip():
                s.summary = ""
                continue
            if _is_boilerplate(summary):
                logger.warning(f"BOILERPLACE DETECTED for story {idx} ({headline}): '{summary[:80]}...' — marking for fallback")
                s.summary = ""
                continue
            if not _has_topic_overlap(summary, headline):
                logger.warning(f"TOPIC MISMATCH for story {idx} ({headline}): summary shares zero keywords — marking for fallback")
                s.summary = ""
                continue
            if _is_valid_summary(summary, headline):
                s.summary = summary
                valid_count += 1
            else:
                s.summary = ""

    except Exception as e:
        logger.warning(f"BATCH SUMMARIZE ERROR ({cat_name}): {e}")
        for s in sub_batch:
            s.summary = ""
        return {'success': False, 'valid_count': 0, 'failed': True}

    return {'success': valid_count > 0, 'valid_count': valid_count, 'failed': valid_count == 0}


async def batch_summarize_all(client, stories, session=None, *, batch_size: int = 3, max_concurrency: int = 1, recovery_max_concurrency: int = 2, recovery_deadline_s: float = 0.0):
    """Async batch summarization with batch retry, individual recovery, fallback, and structured metrics.

    Args:
        client: LLM client with chat_completions_create method
        stories: List of StoryPipelineState objects
        session: Optional HTTP session (unused, kept for API compatibility)
        batch_size: Stories per sub-batch (default 3)
        max_concurrency: Max concurrent sub-batch LLM calls (default 1, serial)

    Returns SummaryMetrics with full accounting of all outcomes.
    """
    if not stories:
        return empty_metrics()

    t_start = time.monotonic()

    # Group by category
    by_category = {}
    for s in stories:
        by_category.setdefault(s.category, []).append(s)

    # Collect all sub-batches
    all_sub_batches = []
    for cat_name, cat_stories in by_category.items():
        for i in range(0, len(cat_stories), batch_size):
            all_sub_batches.append((cat_name, cat_stories[i:i+batch_size]))

    metrics = SummaryMetrics(total_stories=len(stories), sub_batches=len(all_sub_batches))

    # Phase 1: Initial batch dispatch
    batch_results = []
    if max_concurrency > 1:
        sem = asyncio.Semaphore(max_concurrency)
        tasks = [
            _summarize_sub_batch(client, cat_name, sb, semaphore=sem, batch_size=batch_size)
            for cat_name, sb in all_sub_batches
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                cat_name, _ = all_sub_batches[i]
                logger.warning(f"BATCH SUB-BATCH EXCEPTION ({cat_name}): {result}")
                batch_results.append({'success': False, 'valid_count': 0, 'failed': True})
            else:
                batch_results.append(result)
    else:
        for cat_name, sb in all_sub_batches:
            result = await _summarize_sub_batch(client, cat_name, sb, batch_size=batch_size)
            batch_results.append(result)

    metrics.batch_calls = len(all_sub_batches)

    # Phase 2: Retry failed full sub-batches once
    failed_indices = [i for i, r in enumerate(batch_results) if r.get('failed')]

    if failed_indices:
        metrics.batch_retries = len(failed_indices)
        metrics.batch_failures = len(failed_indices)

        # Small backoff before retry
        backoff = LLM_SUMMARY_RETRY_BACKOFF[0] if LLM_SUMMARY_RETRY_BACKOFF else 0.5
        await asyncio.sleep(backoff)

        retry_entries = [(all_sub_batches[i][0], all_sub_batches[i][1]) for i in failed_indices]
        retry_results = []
        if max_concurrency > 1:
            sem = asyncio.Semaphore(max_concurrency)
            retry_tasks = [
                _summarize_sub_batch(client, cat_name, sb, semaphore=sem, batch_size=batch_size)
                for cat_name, sb in retry_entries
            ]
            raw = await asyncio.gather(*retry_tasks, return_exceptions=True)
            for idx, result in enumerate(raw):
                if isinstance(result, Exception):
                    cat_name, _ = retry_entries[idx]
                    logger.warning(f"BATCH RETRY EXCEPTION ({cat_name}): {result}")
                    retry_results.append({'success': False, 'valid_count': 0, 'failed': True})
                else:
                    retry_results.append(result)
        else:
            for cat_name, sb in retry_entries:
                result = await _summarize_sub_batch(client, cat_name, sb, batch_size=batch_size)
                retry_results.append(result)

        metrics.batch_calls += len(failed_indices)

        for idx, result in enumerate(retry_results):
            original_index = failed_indices[idx]
            batch_results[original_index] = result

    # Phase 3: Individual recovery for unresolved stories with bounded concurrency
    needs_recovery = [s for s in stories if not s.summary or not s.summary.strip()]
    recovery_count = 0
    recovery_started = 0

    if needs_recovery:
        deadline_ts = time.monotonic() + recovery_deadline_s if recovery_deadline_s > 0 else None

        async def _recover_one(s):
            nonlocal recovery_count, recovery_started
            recovery_started += 1
            if deadline_ts is not None and time.monotonic() >= deadline_ts:
                return  # Past deadline, skip
            context = build_context(s, preview_chars=LLM_CONTEXT_PREVIEW_CHARS)
            try:
                coro = _summarize(client, context, title=s.title)
                if deadline_ts is not None:
                    remaining = deadline_ts - time.monotonic()
                    if remaining <= 0:
                        return
                    try:
                        retry = await asyncio.wait_for(coro, timeout=remaining)
                    except asyncio.TimeoutError:
                        return
                else:
                    retry = await coro
            except asyncio.CancelledError:
                raise
            except Exception:
                return
            if _is_valid_summary(retry, s.title):
                s.summary = retry
                recovery_count += 1
            elif not s.summary or not s.summary.strip():
                s.summary = _generate_auto_fallback(s.title)

        sem = asyncio.Semaphore(recovery_max_concurrency)

        async def _sem_wrapped(s):
            async with sem:
                await _recover_one(s)

        tasks = [asyncio.create_task(_sem_wrapped(s)) for s in needs_recovery]

        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.warning(f"RECOVERY GATHER ERROR: {e}")

        # Cancel all tasks if deadline is now past
        if deadline_ts is not None and time.monotonic() >= deadline_ts:
            logger.warning(f"[RECOVERY DEADLINE] exhausted after {recovery_deadline_s}s -- cancelling remaining work")
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            # Assign [Auto] to stories still unresolved after cancellation
            for s in needs_recovery:
                if not s.summary or not s.summary.strip():
                    s.summary = _generate_auto_fallback(s.title)

    # Phase 4: Count final outcomes
    auto_fallbacks = 0
    unavailable = 0
    final_valid = 0
    final_invalid = 0

    for s in stories:
        if not s.summary or not s.summary.strip():
            final_invalid += 1
        elif s.summary.strip().startswith("[Summary Unavailable]"):
            unavailable += 1
        elif s.summary.strip().startswith("[Auto]"):
            auto_fallbacks += 1
        else:
            final_valid += 1

    metrics.individual_recovery_attempts = recovery_started
    metrics.individual_recovered = recovery_count
    metrics.auto_fallbacks = auto_fallbacks
    metrics.unavailable_summaries = unavailable
    metrics.final_valid = final_valid
    metrics.final_invalid = final_invalid
    metrics.elapsed_s = time.monotonic() - t_start

    # Logging
    if auto_fallbacks:
        logger.info(f"[AUTO FALLBACK] {auto_fallbacks} stories fell back to [Auto] headline summary")
    if recovery_count:
        logger.info(f"[BATCH RETRY] {recovery_count}/{len(needs_recovery)} empty batch stories recovered via single-story LLM")
    if metrics.batch_retries:
        logger.info(f"[BATCH RETRY] {metrics.batch_retries} sub-batches retried")

    return metrics
