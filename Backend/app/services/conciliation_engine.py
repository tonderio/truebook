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
    Validate Kushki daily summary against Kushki's own "Depósito Neto" formula.

        net = gross
            - commission          (Com. Kushki + IVA)
            - rolling_reserve     (RR Retenido, net of release)
            - rr_released         (separately, since release settles with the gross
                                   then is withheld again by the engine via
                                   rolling_reserve = retained - released)
            + refund              (stored negative → reduces deposit)
            + chargeback          (stored negative)
            + void                (stored negative)
            + manual_adj          (can be either sign)

    All 8 columns are emitted by kushki_parser._MERGE_FIELDS; this function
    simply nets them instead of throwing 5 away.
    """
    daily = kushki_result.get("daily_summary", [])
    matched = []
    differences = []

    for row in daily:
        gross = float(row.get("gross_amount", 0))
        commission = float(row.get("commission", 0))
        rolling = float(row.get("rolling_reserve", 0))
        rr_released = float(row.get("rr_released", 0))
        refund = float(row.get("refund", 0))
        chargeback = float(row.get("chargeback", 0))
        void = float(row.get("void", 0))
        manual_adj = float(row.get("manual_adj", 0))
        net = float(row.get("net_deposit", 0))

        computed_net = round(
            gross - commission - rolling - rr_released
            + refund + chargeback + void + manual_adj,
            6,
        )
        diff = round(abs(computed_net - net), 6)

        entry = {
            "date": row.get("date"),
            "tx_count": row.get("tx_count"),
            "gross_amount": gross,
            "commission": commission,
            "rolling_reserve": rolling,
            "rr_released": rr_released,
            "refund": refund,
            "chargeback": chargeback,
            "void": void,
            "manual_adj": manual_adj,
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
    classifications: Dict[int, str] | None = None,
) -> Dict[str, Any]:
    """
    Cross Kushki SR daily net_deposits against Banregio credits classified
    as `kushki_acquirer`. Match by amount within tolerance.

    Inputs:
      kushki_result["daily_summary"]: list of {date, net_deposit, …}
      banregio_result["movements"]: list of {date, description, credit, debit, …}
      classifications: {movement_index → classification_string}
        When provided, only `kushki_acquirer` credits are eligible matches —
        prevents false positives where a non-Kushki SPEI happens to share an
        amount with a Kushki settlement.

    Falls back through three sources for the Banregio side, in priority order:
      1. classifications (preferred — semantically correct)
      2. banregio_result["deposit_column"] (legacy, position-7 from parser)
      3. banregio_result["movements"][*].credit (last resort, all credits)

    The previous implementation used only #2, which was always-empty for the
    March 2026 Banregio Excel because column index 7 was a non-amount column.
    Kushki vs Banregio always returned 0 matches silently. See the audit
    Section 3.3 results in docs/audits/2026_03_process5.md for the trace.
    """
    # Kushki side: list of {date, net_deposit}
    kushki_deposits = [
        {"date": r["date"], "amount": float(r.get("net_deposit", 0))}
        for r in kushki_result.get("daily_summary", [])
        if float(r.get("net_deposit", 0)) > 0
    ]

    # Banregio side — choose the most specific source available
    movements = banregio_result.get("movements") or []
    if classifications is not None and movements:
        # Preferred: only kushki_acquirer-classified credits
        banregio_deposits = [
            {"amount": float(m.get("credit") or 0), "matched": False, "source": "classified"}
            for idx, m in enumerate(movements)
            if classifications.get(idx) == "kushki_acquirer"
            and float(m.get("credit") or 0) > 0
        ]
    elif banregio_result.get("deposit_column"):
        # Legacy: positional column-H amounts from the parser
        banregio_deposits = [
            {"amount": float(a), "matched": False, "source": "deposit_column"}
            for a in banregio_result.get("deposit_column", [])
            if float(a) > 0
        ]
    elif movements:
        # Last resort: every positive credit. Will produce false positives
        # if non-Kushki SPEIs share amounts with Kushki settlements.
        banregio_deposits = [
            {"amount": float(m.get("credit") or 0), "matched": False, "source": "all_credits"}
            for m in movements
            if float(m.get("credit") or 0) > 0
        ]
    else:
        banregio_deposits = []

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
