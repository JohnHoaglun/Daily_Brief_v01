import logging
import time
from daily_brief.config import (
    LLM_MODEL,
    SYSTEM_ALERT_PROMPT,
    LLM_ALERT_OPTIONS,
)

logger = logging.getLogger(__name__)


def parse_alert_batch_response(response):
    """Parse alert batch response into dict mapping index -> bool."""
    results = {}
    for line in response.split('\n'):
        line = line.strip()
        if line.startswith('STORY_'):
            try:
                parts = line.split(':', 1)
                idx_str = parts[0].replace('STORY_', '')
                val = parts[1].strip().upper()
                idx = int(idx_str)
                results[idx] = (val == "TRUE")
            except (ValueError, IndexError):
                pass
        else:
            # Fallback: <number>: TRUE/FALSE
            parts = line.split(':', 1)
            if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip() in ('TRUE', 'FALSE'):
                idx = int(parts[0].strip())
                results[idx] = (parts[1].strip().upper() == "TRUE")
    return results


def batch_evaluate_alerts(client, stories):
    """Single Ollama call to evaluate ALL stories for alert priority.
    Returns dict mapping index -> True/False."""
    if not stories:
        return {}

    # Group by category to prevent overload and ensure proper handling
    by_category = {}
    for s in stories:
        by_category.setdefault(s.category, []).append(s)

    # Process each category separately to avoid hitting context limits or timeouts
    all_alerts = {}
    for cat_name, cat_stories in by_category.items():
        # Build input text — only include stories that have valid summaries
        labeled_summaries = []
        summary_indices = []  # Track which stories are included
        idx = 0

        for s in cat_stories:
            if not s.summary or s.summary.startswith("[") or "unavailable" in s.summary.lower():
                continue
            label = f"STORY_{idx}"
            entry = f"{label} | Headline: {s.title}\nSummary: {s.summary}"
            labeled_summaries.append(entry)
            s._alert_idx = idx  # Tag the story with its batch index
            summary_indices.append(idx)
            idx += 1

        if not labeled_summaries:
            continue

        alert_text = "\n\n".join(labeled_summaries)

        SYSTEM_ALERT_BATCH = SYSTEM_ALERT_PROMPT

        for attempt in range(2):
            try:
                t0 = time.time()
                r = client.chat_completions_create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_ALERT_BATCH},
                        {"role": "user", "content": alert_text}
                    ],
                    **LLM_ALERT_OPTIONS
                )
                logger.debug(f"BATCH ALERT EVAL ({cat_name}, {len(labeled_summaries)} stories): {time.time() - t0:.2f}s")

                resp_text = r.choices[0].message.content
                alert_results = parse_alert_batch_response(resp_text)

                # Map results back to stories
                alerts_flagged = 0
                for s in cat_stories:
                    if hasattr(s, '_alert_idx') and s._alert_idx in alert_results:
                        s.is_alert = alert_results[s._alert_idx]
                        if s.is_alert:
                            alerts_flagged += 1
                    else:
                        s.is_alert = False

                break  # Success, exit retry loop
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"BATCH ALERT EVAL ({cat_name}) attempt 1 failed ({e}), retrying...")
                    time.sleep(3)
                else:
                    logger.warning(f"BATCH ALERT ERROR ({cat_name}, final): {e}")
                    # Even if we fail, continue to next category - don't crash the whole pipeline
                    for s in cat_stories:
                        s.is_alert = False

    # Build return dict mapping global index -> bool for all stories
    alert_index = {}
    for i, s in enumerate(stories):
        if hasattr(s, "is_alert"):
            alert_index[i] = s.is_alert
        else:
            alert_index[i] = False

    return alert_index
