"""
Conciliation engine.
1. FEES conciliation — consolidate by merchant
2. Kushki daily conciliation
3. Kushki vs Banregio — Column I (Kushki net_deposit) vs Column H (Banregio deposit_ref)

Tolerance is configurable via the reconciliation_config table.
When called from the pipeline, the caller reads the config and passes it in.
The default (0.01) is used as a fallback.
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_TOLERANCE = 0.01


def get_tolerance(db=None, config_key: str = "conciliation_tolerance") -> float:
    """Read tolerance from reconciliation_config table, or return default."""
    if db is None:
        return DEFAULT_TOLERANCE
    try:
        from app.models.alert import ReconciliationConfig
        config = db.query(ReconciliationConfig).filter(
            ReconciliationConfig.config_key == config_key
        ).first()
        if config:
            return float(config.config_value)
    except Exception:
        pass
    return DEFAULT_TOLERANCE


def conciliate_fees(fees_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate FEES consolidation:
    tx fees + withdrawal fees + refund fees = total fees.
    """
    merchant_summary = fees_result.get("merchant_summary", [])
    withdrawals = fees_result.get("withdrawals_summary", [])
    refunds = fees_result.get("refunds_summary", [])

    matched = []
    differences = []

    for merchant in merchant_summary:
        mid = merchant["merchant_id"]
        tx_fee = merchant.get("total_fee", 0)
        w_fee = next((w["total_fee"] for w in withdrawals if w.get("merchant_id") == mid), 0)
        r_fee = next((r["total_fee"] for r in refunds if r.get("merchant_id") == mid), 0)
        total = round(tx_fee + w_fee + r_fee, 6)

        matched.append({
            "merchant_id": mid,
            "merchant_name": merchant.get("merchant_name"),
            "tx_fee": round(tx_fee, 6),
            "withdrawal_fee": round(w_fee, 6),
            "refund_fee": round(r_fee, 6),
            "total_fee": total,
        })

    total_conciliated = sum(m["total_fee"] for m in matched)

    return {
        "matched": matched,
        "differences": differences,
        "unmatched_kushki": [],
        "unmatched_banregio": [],
        "total_conciliated": round(total_conciliated, 6),
        "total_difference": 0.0,
    }


def conciliate_kushki_daily(
    kushki_result: Dict[str, Any],
    tolerance: float = DEFAULT_TOLERANCE,
) -> Dict[str, Any]:
    """
    Validate Kushki daily summary:
    gross - commission - rolling_reserve = net_deposit per day.
    """
    daily = kushki_result.get("daily_summary", [])
    matched = []
    differences = []

    for row in daily:
        gross = float(row.get("gross_amount", 0))
        commission = float(row.get("commission", 0))
        rolling = float(row.get("rolling_reserve", 0))
        net = float(row.get("net_deposit", 0))
        computed_net = round(gross - commission - rolling, 6)
        diff = round(abs(computed_net - net), 6)

        entry = {
            "date": row.get("date"),
            "tx_count": row.get("tx_count"),
            "gross_amount": gross,
            "commission": commission,
            "rolling_reserve": rolling,
            "net_deposit": net,
            "computed_net": computed_net,
            "difference": diff,
        }
        if diff <= tolerance:
            matched.append(entry)
        else:
            differences.append(entry)

    total_conciliated = sum(r["net_deposit"] for r in matched)
    total_difference = sum(r["difference"] for r in differences)

    return {
        "matched": matched,
        "differences": differences,
        "unmatched_kushki": [],
        "unmatched_banregio": [],
        "total_conciliated": round(total_conciliated, 6),
        "total_difference": round(total_difference, 6),
    }


def conciliate_kushki_vs_banregio(
    kushki_result: Dict[str, Any],
    banregio_result: Dict[str, Any],
    tolerance: float = DEFAULT_TOLERANCE,
) -> Dict[str, Any]:
    """
    Cross Kushki Column I (net_deposit per day) vs Banregio Column H (deposit_ref).
    Match by amount within tolerance.
    """
    # Kushki side: list of {date, net_deposit}
    kushki_deposits = [
        {"date": r["date"], "amount": float(r.get("net_deposit", 0))}
        for r in kushki_result.get("daily_summary", [])
        if float(r.get("net_deposit", 0)) > 0
    ]

    # Banregio side: list of deposit amounts from column H
    banregio_deposits = [
        {"amount": float(a), "matched": False}
        for a in banregio_result.get("deposit_column", [])
        if float(a) > 0
    ]

    matched = []
    unmatched_kushki = []

    for k in kushki_deposits:
        found = False
        for b in banregio_deposits:
            if not b["matched"] and abs(b["amount"] - k["amount"]) <= tolerance:
                matched.append({
                    "date": k["date"],
                    "kushki_amount": k["amount"],
                    "banregio_amount": b["amount"],
                    "difference": round(abs(b["amount"] - k["amount"]), 6),
                })
                b["matched"] = True
                found = True
                break
        if not found:
            unmatched_kushki.append(k)

    unmatched_banregio = [b for b in banregio_deposits if not b["matched"]]

    total_conciliated = sum(m["kushki_amount"] for m in matched)
    total_difference = sum(m["difference"] for m in matched)

    return {
        "matched": matched,
        "differences": [],
        "unmatched_kushki": unmatched_kushki,
        "unmatched_banregio": [{"amount": b["amount"]} for b in unmatched_banregio],
        "total_conciliated": round(total_conciliated, 6),
        "total_difference": round(total_difference, 6),
        "stats": {
            "total_matched": len(matched),
            "total_unmatched_kushki": len(unmatched_kushki),
            "total_unmatched_banregio": len(unmatched_banregio),
        },
    }


def compute_adjusted_delta(
    delta_bruto: float,
    adjustments: List[Dict],
    conciliation_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Layer approved adjustments on top of a raw delta to compute adjusted delta.

    Args:
        delta_bruto: The raw conciliation difference
        adjustments: List of approved RunAdjustment dicts with keys:
            direction (ADD/SUBTRACT), amount, affects (expected/received/delta)
        conciliation_type: Filter adjustments to this conciliation type (optional)

    Returns:
        {delta_bruto, delta_ajustado, adjustments_applied, net_adjustment}
    """
    applied = []
    net_adjustment = 0.0

    for adj in adjustments:
        # Filter by conciliation type if specified
        if conciliation_type and adj.get("conciliation_type") != conciliation_type:
            continue

        amount = float(adj.get("amount", 0))
        direction = adj.get("direction", "")

        if direction == "ADD":
            net_adjustment += amount
        elif direction == "SUBTRACT":
            net_adjustment -= amount

        applied.append({
            "id": adj.get("id"),
            "type": adj.get("adjustment_type"),
            "direction": direction,
            "amount": amount,
            "description": adj.get("description", ""),
        })

    delta_ajustado = delta_bruto + net_adjustment

    return {
        "delta_bruto": round(delta_bruto, 2),
        "delta_ajustado": round(delta_ajustado, 2),
        "net_adjustment": round(net_adjustment, 2),
        "adjustments_applied": applied,
        "adjustments_count": len(applied),
    }
