import logging
import re
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

from daily_brief.http_client import _fetch_text
from daily_brief.utils import _coerce_percent, _safe_text

logger = logging.getLogger(__name__)


async def _extract_lake_value(
    session,
    key: str,
    url: str,
    reference: datetime,
) -> dict:
    """
    Scrape reservoir level tables from a Texas water data site and return
    percentage values for today, one week ago, and 30 days ago.

    Returns a dict with keys ``today``, ``one_week_ago``, ``thirty_days_ago``
    (each either a percent string or ``None``).
    """
    today = reference.date()
    result: dict = {
        "today": None,
        "one_week_ago": None,
        "thirty_days_ago": None,
    }
    targets = [
        ("today", today),
        ("one_week_ago", today - timedelta(days=7)),
        ("thirty_days_ago", today - timedelta(days=30)),
    ]

    html = await _fetch_text(session, url)
    if not html:
        logger.warning("Lake data unavailable (%s): no html.", key)
        return result

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    parsed_pairs: list = []

    for row in soup.select("tbody tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        if len(cells) < 3:
            continue
        label: str = _safe_text(cells[0]).strip().lower()
        raw_date: str = _safe_text(cells[1]).strip()
        raw_percent: str = _safe_text(cells[2]).strip()
        percent = _coerce_percent(raw_percent)
        if not percent:
            continue

        if "today" in label or "current" in label:
            result["today"] = percent
        elif "1 week ago" in label or "week ago" in label or "7 day" in label:
            result["one_week_ago"] = percent
        elif (
            "30 days ago" in label
            or "thirty days ago" in label
            or "1 month ago" in label
            or "30d" in label
        ):
            result["thirty_days_ago"] = percent

        try:
            row_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            parsed_pairs.append((row_date, percent))
        except Exception:
            pass

    # Map by date when label values are missing.
    for label, target_date in targets:
        if result.get(label):
            continue
        exact = next((val for d, val in parsed_pairs if d == target_date), None)
        if exact:
            result[label] = exact
            continue
        if not parsed_pairs:
            break
        before = [d_val for d_val in parsed_pairs if d_val[0] <= target_date]
        candidates = before if before else parsed_pairs
        pick = min(candidates, key=lambda pair: abs((pair[0] - target_date).days))
        result[label] = pick[1]

    # Legacy fallback path if table parsing fails.
    if any(v is None for v in result.values()):
        for m in re.finditer(r"(\d{1,3}(?:\.\d+)?)\s*%", text):
            all_pct = _coerce_percent(m.group(1))
            if all_pct is not None and result["today"] is None:
                result["today"] = all_pct
            elif all_pct is not None and result["one_week_ago"] is None:
                result["one_week_ago"] = all_pct
            elif all_pct is not None and result["thirty_days_ago"] is None:
                result["thirty_days_ago"] = all_pct

    return result
