"""
Bitso-Banregio matching engine.

Finds candidate Banregio movements that could correspond to Bitso deposits,
and manages the match confirmation workflow.
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def find_candidates(
    bitso_line: Dict[str, Any],
    banregio_movements: List[Dict[str, Any]],
    existing_classifications: Dict[int, str],
    existing_matches: set,
    tolerance_amount: float = 1.00,
    tolerance_days: int = 3,
) -> List[Dict[str, Any]]:
    """
    Find Banregio movements that could match a Bitso report line.

    Args:
        bitso_line: {txn_date (date), net_amount (float), merchant_name, ...}
        banregio_movements: List of movements from BanregioResult.movements JSON
        existing_classifications: {movement_index: classification} for already-classified movements
        existing_matches: Set of banregio_movement_index values already matched to Bitso
        tolerance_amount: Max difference in MXN (from reconciliation_config)
        tolerance_days: Max date distance in days (from reconciliation_config)

    Returns:
        Sorted list of candidates: [{banregio_movement_index, movement_date,
            movement_description, movement_amount, delta, date_distance_days, confidence}]
    """
    bitso_date = bitso_line.get("txn_date")
    bitso_amount = float(bitso_line.get("net_amount", 0) or bitso_line.get("gross_amount", 0))

    if bitso_amount == 0:
        return []

    candidates = []

    for idx, mov in enumerate(banregio_movements):
        # Skip movements already matched to another Bitso line
        if idx in existing_matches:
            continue

        # Skip movements already classified as another acquirer (not unclassified/bitso)
        cls = existing_classifications.get(idx, "unclassified")
        if cls not in ("unclassified", "bitso", "other"):
            continue

        # Only consider credit (abono) movements for deposits
        credit = float(mov.get("credit", 0) or 0)
        if credit <= 0:
            continue

        # Check amount tolerance
        amount_delta = abs(credit - bitso_amount)
        if amount_delta > tolerance_amount:
            continue

        # Check date tolerance
        mov_date = _parse_movement_date(mov.get("date"))
        if bitso_date and mov_date:
            date_distance = abs((mov_date - bitso_date).days)
            if date_distance > tolerance_days:
                continue
        elif bitso_date is None and mov_date:
            # Bitso date unavailable — allow match but mark as low confidence
            date_distance = tolerance_days  # max penalty
        elif mov_date is None:
            date_distance = tolerance_days  # max penalty
        else:
            # Both dates None — allow match with max date penalty
            date_distance = tolerance_days

        # Compute confidence
        confidence = _compute_confidence(amount_delta, date_distance, tolerance_amount)

        candidates.append({
            "banregio_movement_index": idx,
            "movement_date": mov.get("date"),
            "movement_description": mov.get("description", ""),
            "movement_amount": credit,
            "delta": round(credit - bitso_amount, 2),
            "date_distance_days": date_distance,
            "confidence": confidence,
        })

    # Sort: exact amount first, then closest date, then highest confidence
    candidates.sort(key=lambda c: (abs(c["delta"]), c["date_distance_days"]))

    return candidates


def find_all_candidates(
    bitso_lines: List[Dict[str, Any]],
    banregio_movements: List[Dict[str, Any]],
    existing_classifications: Dict[int, str],
    existing_matches: set,
    tolerance_amount: float = 1.00,
    tolerance_days: int = 3,
) -> Dict[int, List[Dict[str, Any]]]:
    """
    Find candidates for all unmatched Bitso lines.

    Returns: {bitso_line_id: [candidates]}
    """
    result = {}
    for line in bitso_lines:
        line_id = line.get("id") or line.get("line_index")
        candidates = find_candidates(
            bitso_line=line,
            banregio_movements=banregio_movements,
            existing_classifications=existing_classifications,
            existing_matches=existing_matches,
            tolerance_amount=tolerance_amount,
            tolerance_days=tolerance_days,
        )
        result[line_id] = candidates

    return result


def build_adjustment_suggestion(
    bitso_amount: float,
    banregio_amount: float,
    process_id: int,
    merchant_name: Optional[str] = None,
    match_date: Optional[date] = None,
    tolerance_amount: float = 1.00,
) -> Optional[Dict[str, Any]]:
    """
    If a confirmed match has a delta exceeding the configured tolerance,
    return a pre-populated MANUAL_BITSO adjustment suggestion.

    Per spec QA-07: delta within tolerance ($1.00 default) → no suggestion.
    """
    delta = round(banregio_amount - bitso_amount, 2)
    if abs(delta) <= tolerance_amount:
        return None

    direction = "ADD" if delta > 0 else "SUBTRACT"
    merchant_label = f" ({merchant_name})" if merchant_name else ""

    return {
        "adjustment_type": "MANUAL_BITSO",
        "direction": direction,
        "amount": abs(delta),
        "currency": "MXN",
        "affects": "received",
        "conciliation_type": "bitso_vs_banregio",
        "merchant_name": merchant_name,
        "adjustment_date": str(match_date) if match_date else None,
        "description": (
            f"Diferencia en cruce Bitso-Banregio{merchant_label}: "
            f"Bitso ${bitso_amount:,.2f} vs Banregio ${banregio_amount:,.2f} "
            f"(delta ${delta:,.2f})"
        ),
    }


def _parse_movement_date(date_str: Any) -> Optional[date]:
    """Parse a date from Banregio movement's date field."""
    if date_str is None:
        return None
    if isinstance(date_str, date):
        return date_str

    from datetime import datetime
    s = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _compute_confidence(
    amount_delta: float,
    date_distance: int,
    tolerance_amount: float,
) -> str:
    """
    Compute match confidence based on amount and date proximity.
    Returns: 'high', 'medium', or 'low'
    """
    if amount_delta <= 0.01 and date_distance <= 1:
        return "high"
    elif amount_delta <= tolerance_amount * 0.5 and date_distance <= 2:
        return "medium"
    else:
        return "low"
