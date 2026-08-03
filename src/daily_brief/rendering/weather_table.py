import logging

from daily_brief.utils import _present_weather_value
from daily_brief.config import WEATHER_SECTION_TITLE, WEATHER_LABELS, WEATHER_LAKE_URLS

logger = logging.getLogger(__name__)


def build_weather_markdown(weather):
    rows = weather.get("forecast", [])
    if not rows:
        rows = [
            {"date": "Dynamic", "day": "Dynamic", "night": "Dynamic", "high": "Dynamic", "low": "Dynamic", "precip": "Dynamic", "wind": "Dynamic"}
        ] * 3
    if len(rows) < 3:
        rows.extend([{"date": "Dynamic", "day": "Dynamic", "night": "Dynamic", "high": "Dynamic", "low": "Dynamic", "precip": "Dynamic", "wind": "Dynamic"}] * (3 - len(rows)))

    md = []
    md.append("")
    md.append("---")
    md.append(f"## {WEATHER_SECTION_TITLE}")
    md.append("")
    md.append("**3 Day forecast for 77316:**")
    md.append("")
    md.append("| **Date** | **Day Condition** | **Night Condition** | **High Temp** | **Low Temp** | **Precip. Chance** | **Wind** |")
    md.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in rows[:3]:
        md.append(
            "| "
            f"{_present_weather_value(row.get('date'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('day'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('night'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('high'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('low'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('precip'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('wind'), 'Unavailable')} |"
        )

    md.append("")
    station = weather.get("station", {})
    station_rows = WEATHER_LABELS.get('station_rows', [])
    _default_station_rows = ["Climate Normal High for today 77316", "Average Monthly rainfall for 77316", "Current Monthly rainfall for 77316"]
    def _row(i, key, default_idx=0):
        return (station_rows[i] if i < len(station_rows) else _default_station_rows[default_idx]), station.get(key)
    r0 = _row(0, 'avg_temp_today', 0)
    r1 = _row(1, 'avg_monthly_rainfall', 1)
    r2 = _row(2, 'current_monthly_rainfall', 2)
    md.append(f"| {r0[0]} | {_present_weather_value(r0[1], 'Unavailable')} |")
    md.append("| --- | --- |")
    md.append(f"| {r1[0]} | {_present_weather_value(r1[1], 'Unavailable')} |")
    md.append(f"| {r2[0]} | {_present_weather_value(r2[1], 'Unavailable')} |")
    md.append("")
    md.append("| Where | Today | 1 Week Ago | 30 Days ago |")
    md.append("| --- | --- | --- | --- |")
    def _lake_label(k):
        base = k.replace("_", " ").replace("-", " ").title()
        return f"Lake {base}" if not base.startswith("Lake") else base
    for key in (WEATHER_LAKE_URLS or {}):
        label = _lake_label(key)
        vals = weather.get("lakes", {}).get(key, {})
        md.append(
            f"| {label} | {_present_weather_value(vals.get('today'), 'Unavailable')} | "
            f"{_present_weather_value(vals.get('one_week_ago'), 'Unavailable')} | "
            f"{_present_weather_value(vals.get('thirty_days_ago'), 'Unavailable')} |"
        )

    md.append("")
    md.append("---")
    return md
