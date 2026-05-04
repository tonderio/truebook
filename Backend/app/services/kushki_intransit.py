"""
In-transit Kushki deposit detection (spec v2 §5.2, criterio caja).

Kushki's settlement reports include rows where `fecha_pago` falls *after*
the period end — those represent transactions processed in the period
but liquidated D+1 / next month. Cash-basis accounting requires
**excluding them from the current month's cuadre** while documenting
them so the next month picks them up correctly.

This module classifies the daily_summary rows already extracted by
`kushki_parser.py` into:
  - intra-month: fecha_pago within [period_start, period_end]
  - in-transit:  fecha_pago > period_end (typically day 1 of next month)

It does NOT re-parse files; it operates on the already-parsed
`KushkiResult.daily_summary` so it benefits from every parser fix
(e.g. the TOTAL-row filter we landed earlier).

Returns a structured payload that:
  - drives the `TIMING_CAJA` alert (spec §4.3.3)
  - feeds row 4 of the Kushki cuadre block (spec §4.2.2 Bloque 3)
  - lets the v2 Excel exporter document the transit explicitly
"""
from __future__ import annotations

import calendar
import logging
import re
from datetime import date
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# Acceptable date-string formats encountered in Kushki files
_DATE_FORMATS_RE = [
    re.compile(r"^(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})"),    # 2026-03-24
    re.compile(r"^(?P<d>\d{2})/(?P<m>\d{2})/(?P<y>\d{4})"),    # 24/03/2026
    re.compile(r"^(?P<m>\d{2})/(?P<d>\d{2})/(?P<y>\d{4})"),    # 03/24/2026 — fallback
]


def parse_kushki_date(value: Any) -> date | None:
    """Best-effort parse of a fecha_pago string/timestamp.

    Returns None if unparseable — the caller should treat that row as
    non-classifiable rather than crashing.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None

    # ISO timestamps like "2026-03-24 00:00:00"
    if " " in s:
        s = s.split(" ", 1)[0]
    if "T" in s:
        s = s.split("T", 1)[0]

    for rx in _DATE_FORMATS_RE:
        m = rx.match(s)
        if m:
            try:
                y = int(m.group("y"))
                mo = int(m.group("m"))
                d = int(m.group("d"))
                return date(y, mo, d)
            except (ValueError, TypeError):
                continue
    return None


def period_bounds(period_year: int, period_month: int) -> tuple[date, date]:
    """First and last calendar day of the period (inclusive)."""
    last_day = calendar.monthrange(period_year, period_month)[1]
    return date(period_year, period_month, 1), date(period_year, period_month, last_day)


def classify_rows(
    daily_summary: Iterable[dict],
    period_year: int,
    period_month: int,
) -> dict[str, Any]:
    """Split daily_summary rows into intra-month, in-transit, and pre-period.

    Args:
        daily_summary: list of rows from `KushkiResult.daily_summary`. Each row
            must have at least `date` and `net_deposit` keys; other numeric
            fields are passed through.
        period_year, period_month: the period being reconciled.

    Returns:
        {
          "period_start": date,
          "period_end":   date,
          "intra_month": {
              "rows": [...],            # rows whose fecha_pago is in [start, end]
              "total_net_deposit": float,
              "row_count": int,
          },
          "in_transit": {
              "rows": [...],            # fecha_pago > period_end
              "total_net_deposit": float,
              "row_count": int,
          },
          "pre_period": {
              "rows": [...],            # fecha_pago < period_start (rare)
              "total_net_deposit": float,
              "row_count": int,
          },
          "unparseable_rows": [...],    # rows whose date couldn't be parsed
          "has_in_transit": bool,        # convenience flag for the alert engine
        }
    """
    start, end = period_bounds(period_year, period_month)

    intra: list[dict] = []
    transit: list[dict] = []
    pre: list[dict] = []
    bad: list[dict] = []

    for row in daily_summary or []:
        d = parse_kushki_date(row.get("date"))
        annotated = dict(row)
        if d is None:
            bad.append(annotated)
            continue

        annotated["_parsed_date"] = d.isoformat()
        if d < start:
            pre.append(annotated)
        elif d > end:
            transit.append(annotated)
        else:
            intra.append(annotated)

    def _sum(rows: list[dict]) -> float:
        return round(sum(float(r.get("net_deposit") or 0) for r in rows), 2)

    payload = {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "intra_month": {
            "rows": intra,
            "total_net_deposit": _sum(intra),
            "row_count": len(intra),
        },
        "in_transit": {
            "rows": transit,
            "total_net_deposit": _sum(transit),
            "row_count": len(transit),
        },
        "pre_period": {
            "rows": pre,
            "total_net_deposit": _sum(pre),
            "row_count": len(pre),
        },
        "unparseable_rows": bad,
        "has_in_transit": len(transit) > 0,
    }

    if bad:
        logger.warning(
            "kushki_intransit: %d row(s) had unparseable fecha_pago — excluded from all buckets",
            len(bad),
        )
    if transit:
        logger.info(
            "kushki_intransit: %d in-transit row(s) totalling $%.2f (period %s-%02d)",
            len(transit), payload["in_transit"]["total_net_deposit"],
            period_year, period_month,
        )

    return payload


def summary_for_alert(classification: dict) -> dict:
    """Compact summary for the TIMING_CAJA alert + Excel cuadre row 4.

    Returns the fields the alert engine and the v2 exporter need without
    pulling in the full row arrays.
    """
    transit = classification.get("in_transit", {})
    return {
        "period_start": classification.get("period_start"),
        "period_end": classification.get("period_end"),
        "transit_total": transit.get("total_net_deposit", 0.0),
        "transit_row_count": transit.get("row_count", 0),
        "transit_dates": [r.get("_parsed_date") for r in transit.get("rows", [])],
        "intra_month_total": classification.get("intra_month", {}).get("total_net_deposit", 0.0),
    }
