"""
Warren Audit — Cross-validation of acquirer deposits vs Banregio movements.

For each acquirer, matches their reported deposits against the corresponding
Banregio bank statement entries. Normalizes dates across formats, computes
deltas, and returns a verdict: VERIFIED or DISCREPANCY.

This is Warren's first real intelligence job — proving that every peso
the acquirers say they deposited actually arrived in the bank.
"""
import logging
import re
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.result import KushkiResult, BanregioResult
from app.models.classification import BanregioMovementClassification

logger = logging.getLogger(__name__)

# ── Date normalization ────────────────────────────────────────────────

DATE_FORMATS = [
    "%Y-%m-%d",       # 2026-03-02
    "%d/%m/%Y",       # 02/03/2026
    "%m/%d/%Y",       # 03/02/2026
    "%Y-%m-%d %H:%M:%S",  # 2026-03-02 00:00:00
]


def _normalize_date(val: Any) -> Optional[str]:
    """Parse any date format into YYYY-MM-DD string. Returns None for garbage."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", ""):
        return None
    # Skip TOTAL/summary rows
    if "TOTAL" in s.upper() or len(s) > 20:
        return None

    for fmt in DATE_FORMATS:
        try:
            d = datetime.strptime(s, fmt)
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Try extracting date from longer strings like "  2026-03-02"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    return None


def _is_in_month(date_str: str, year: int, month: int) -> bool:
    """Check if a YYYY-MM-DD date is within the target month."""
    if not date_str:
        return False
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d.year == year and d.month == month
    except ValueError:
        return False


# ── Main audit function ───────────────────────────────────────────────

def audit_acquirer_vs_banregio(
    process_id: int,
    db: Session,
) -> Dict[str, Any]:
    """
    Cross-validate all acquirer deposits against Banregio movements.

    Returns:
    {
        "acquirers": [
            {
                "name": "kushki",
                "matches": [
                    {"date": "2026-03-02", "acquirer_amount": 6681217.04,
                     "banregio_amount": 6681217.04, "delta": 0, "status": "MATCHED"}
                ],
                "summary": {
                    "acquirer_total": 73470285.75,
                    "banregio_total": 73470285.75,
                    "delta": 0.00,
                    "matched": 21, "mismatched": 0,
                    "unmatched_acquirer": 0, "unmatched_banregio": 0,
                    "verdict": "VERIFIED"
                }
            }
        ],
        "overall_verdict": "VERIFIED" | "DISCREPANCY"
    }
    """
    process_model = db.execute(
        db.query(KushkiResult).filter(KushkiResult.process_id == process_id).statement
    ).first()

    # Get process period
    from app.models.process import AccountingProcess
    proc = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
    if not proc:
        return {"acquirers": [], "overall_verdict": "NO_DATA"}
    target_year = proc.period_year
    target_month = proc.period_month

    # Load Banregio data
    banregio = db.query(BanregioResult).filter(
        BanregioResult.process_id == process_id
    ).first()
    movements = banregio.movements if banregio else []

    # Load classifications
    classifications = db.query(BanregioMovementClassification).filter(
        BanregioMovementClassification.process_id == process_id
    ).all()
    cls_map = {c.movement_index: c for c in classifications}

    # Build Banregio deposits by acquirer
    banregio_by_acquirer = {}
    for idx, mov in enumerate(movements):
        cls = cls_map.get(idx)
        if not cls or not cls.acquirer:
            continue
        acq = cls.acquirer
        if acq not in banregio_by_acquirer:
            banregio_by_acquirer[acq] = []

        norm_date = _normalize_date(mov.get("date"))
        credit = float(mov.get("credit", 0) or 0)
        if credit > 0 and norm_date:
            banregio_by_acquirer[acq].append({
                "date": norm_date,
                "amount": round(credit, 2),
                "description": mov.get("description", ""),
                "index": idx,
                "matched": False,
            })

    results = []

    # ── Kushki audit (daily detail available) ─────────────────────────
    kushki = db.query(KushkiResult).filter(
        KushkiResult.process_id == process_id
    ).first()

    if kushki and kushki.daily_summary:
        kushki_days = []
        for d in kushki.daily_summary:
            norm_date = _normalize_date(d.get("date"))
            net = float(d.get("net_deposit", 0) or 0)
            if norm_date and net > 0 and _is_in_month(norm_date, target_year, target_month):
                kushki_days.append({
                    "date": norm_date,
                    "amount": round(net, 2),
                    "tx_count": d.get("tx_count", 0),
                    "gross_amount": d.get("gross_amount", 0),
                    "commission": d.get("commission", 0),
                    "matched": False,
                })

        banregio_kushki = banregio_by_acquirer.get("kushki", [])
        matches = _match_deposits(kushki_days, banregio_kushki)
        results.append(_build_acquirer_result("kushki", kushki_days, banregio_kushki, matches))

    # ── Other acquirers (total comparison only) ───────────────────────
    for acq_name in ["bitso", "pagsmile", "unlimit", "stp"]:
        banregio_acq = banregio_by_acquirer.get(acq_name, [])
        if not banregio_acq:
            continue
        # No acquirer-side report — just validate Banregio has entries
        results.append({
            "name": acq_name,
            "matches": [
                {
                    "date": dep["date"],
                    "acquirer_amount": None,
                    "banregio_amount": dep["amount"],
                    "delta": 0,
                    "status": "BANREGIO_ONLY",
                    "description": dep["description"],
                }
                for dep in banregio_acq
            ],
            "summary": {
                "acquirer_total": None,
                "banregio_total": round(sum(d["amount"] for d in banregio_acq), 2),
                "delta": None,
                "matched": 0,
                "mismatched": 0,
                "unmatched_acquirer": 0,
                "unmatched_banregio": len(banregio_acq),
                "verdict": "NO_ACQUIRER_REPORT",
                "note": f"{len(banregio_acq)} depósitos en Banregio. Sin reporte del adquirente para cruzar.",
            },
        })

    # Overall verdict
    verdicts = [r["summary"]["verdict"] for r in results]
    if all(v == "VERIFIED" for v in verdicts):
        overall = "VERIFIED"
    elif any(v == "DISCREPANCY" for v in verdicts):
        overall = "DISCREPANCY"
    else:
        overall = "PARTIAL"

    return {
        "acquirers": results,
        "overall_verdict": overall,
        "period": f"{target_year}-{target_month:02d}",
    }


def _match_deposits(
    acquirer_deposits: List[Dict],
    banregio_deposits: List[Dict],
    tolerance: float = 0.01,
) -> List[Dict]:
    """Match acquirer deposits to Banregio by date + amount."""
    matches = []

    for acq in acquirer_deposits:
        best_match = None
        for ban in banregio_deposits:
            if ban["matched"]:
                continue
            if acq["date"] == ban["date"] and abs(acq["amount"] - ban["amount"]) <= tolerance:
                best_match = ban
                break

        if best_match:
            acq["matched"] = True
            best_match["matched"] = True
            matches.append({
                "date": acq["date"],
                "acquirer_amount": acq["amount"],
                "banregio_amount": best_match["amount"],
                "delta": round(best_match["amount"] - acq["amount"], 2),
                "status": "MATCHED",
                "description": best_match.get("description", ""),
            })
        else:
            # Try amount-only match (date might differ by 1 day)
            for ban in banregio_deposits:
                if ban["matched"]:
                    continue
                if abs(acq["amount"] - ban["amount"]) <= tolerance:
                    acq["matched"] = True
                    ban["matched"] = True
                    matches.append({
                        "date": acq["date"],
                        "acquirer_amount": acq["amount"],
                        "banregio_amount": ban["amount"],
                        "delta": round(ban["amount"] - acq["amount"], 2),
                        "status": "MATCHED_AMOUNT_ONLY",
                        "note": f"Fechas difieren: Kushki={acq['date']}, Banregio={ban['date']}",
                        "description": ban.get("description", ""),
                    })
                    break

        if not acq["matched"]:
            matches.append({
                "date": acq["date"],
                "acquirer_amount": acq["amount"],
                "banregio_amount": None,
                "delta": acq["amount"],
                "status": "UNMATCHED_ACQUIRER",
            })

    # Remaining unmatched Banregio
    for ban in banregio_deposits:
        if not ban["matched"]:
            matches.append({
                "date": ban["date"],
                "acquirer_amount": None,
                "banregio_amount": ban["amount"],
                "delta": ban["amount"],
                "status": "UNMATCHED_BANREGIO",
                "description": ban.get("description", ""),
            })

    matches.sort(key=lambda m: m["date"])
    return matches


def _build_acquirer_result(
    name: str,
    acquirer_deposits: List[Dict],
    banregio_deposits: List[Dict],
    matches: List[Dict],
) -> Dict:
    """Build the audit result for one acquirer."""
    matched = [m for m in matches if m["status"] in ("MATCHED", "MATCHED_AMOUNT_ONLY")]
    mismatched = [m for m in matches if m["status"] == "AMOUNT_MISMATCH"]
    unmatched_acq = [m for m in matches if m["status"] == "UNMATCHED_ACQUIRER"]
    unmatched_ban = [m for m in matches if m["status"] == "UNMATCHED_BANREGIO"]

    acq_total = round(sum(d["amount"] for d in acquirer_deposits if d.get("amount")), 2)
    ban_total = round(sum(d["amount"] for d in banregio_deposits if d.get("amount")), 2)

    verdict = "VERIFIED" if len(mismatched) == 0 and len(unmatched_acq) == 0 and len(unmatched_ban) == 0 else "DISCREPANCY"

    return {
        "name": name,
        "matches": matches,
        "summary": {
            "acquirer_total": acq_total,
            "banregio_total": ban_total,
            "delta": round(ban_total - acq_total, 2),
            "matched": len(matched),
            "mismatched": len(mismatched),
            "unmatched_acquirer": len(unmatched_acq),
            "unmatched_banregio": len(unmatched_ban),
            "verdict": verdict,
        },
    }
