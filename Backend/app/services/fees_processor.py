"""
FEES TONDER processor.
Consolidates transactions, withdrawals, refunds and computes final FEES report.
"""
import logging
from decimal import Decimal
from typing import List, Dict, Any
from collections import defaultdict
from datetime import timezone, timedelta

logger = logging.getLogger(__name__)

TZ_OFFSET = timedelta(hours=6)


def _to_local_date(dt) -> str:
    """Convert UTC datetime to UTC-6 date string."""
    if dt is None:
        return "unknown"
    if hasattr(dt, "astimezone"):
        local = dt.astimezone(timezone(timedelta(hours=-6)))
        return local.strftime("%Y-%m-%d")
    return str(dt)[:10]


def _to_float(value) -> float:
    """Convert any numeric type (including MongoDB Decimal128) to float."""
    if value is None:
        return 0.0
    try:
        # Decimal128 from pymongo has a .to_decimal() method
        if hasattr(value, 'to_decimal'):
            return float(value.to_decimal())
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def recompute_fee(amount: float, msa: float) -> float:
    """Recompute fee from MSA percentage when fee_amount=0 or is_fees_computed=False."""
    if not msa or msa <= 0:
        return 0.0
    return round(float(amount) * float(msa) / 100, 6)


def process_transactions(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Process payment transactions:
    - Recompute fees where needed
    - Group by merchant and date
    Returns merchant_summary and daily_breakdown
    """
    merchant_totals = defaultdict(lambda: {"tx_count": 0, "gross_amount": 0.0, "total_fee": 0.0})
    daily_rows = []

    for tx in transactions:
        merchant_id = tx.get("merchant_id", "unknown")
        merchant_name = tx.get("merchant_name", merchant_id)
        amount = _to_float(tx.get("amount", 0))
        fee_amount = _to_float(tx.get("fee_amount", 0))
        is_fees_computed = tx.get("is_fees_computed", True)
        msa = _to_float(tx.get("msa", 0))

        # Recompute if fee is 0 or not computed
        if fee_amount == 0 or not is_fees_computed:
            fee_amount = recompute_fee(amount, msa)

        date_str = _to_local_date(tx.get("created_at"))
        acquirer = tx.get("acquirer_name", "")

        merchant_totals[merchant_id]["merchant_name"] = merchant_name
        merchant_totals[merchant_id]["tx_count"] += 1
        merchant_totals[merchant_id]["gross_amount"] += amount
        merchant_totals[merchant_id]["total_fee"] += fee_amount

        daily_rows.append({
            "date": date_str,
            "merchant_id": merchant_id,
            "merchant_name": merchant_name,
            "acquirer": acquirer,
            "amount": round(amount, 6),
            "fee_amount": round(fee_amount, 6),
        })

    merchant_summary = [
        {
            "merchant_id": mid,
            "merchant_name": data["merchant_name"],
            "tx_count": data["tx_count"],
            "gross_amount": round(data["gross_amount"], 6),
            "total_fee": round(data["total_fee"], 6),
        }
        for mid, data in merchant_totals.items()
    ]
    merchant_summary.sort(key=lambda x: x["total_fee"], reverse=True)

    return {"merchant_summary": merchant_summary, "daily_breakdown": daily_rows}


def process_withdrawals(withdrawals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group withdrawals by merchant."""
    merchant_totals = defaultdict(lambda: {"count": 0, "total_amount": 0.0, "total_fee": 0.0})

    for w in withdrawals:
        mid = w.get("merchant_id", "unknown")
        amount = _to_float(w.get("amount", 0))
        fee_amount = _to_float(w.get("fee_amount", 0))
        msa = _to_float(w.get("msa", 0))

        if fee_amount == 0:
            fee_amount = recompute_fee(amount, msa)

        merchant_totals[mid]["merchant_name"] = w.get("merchant_name", mid)
        merchant_totals[mid]["count"] += 1
        merchant_totals[mid]["total_amount"] += amount
        merchant_totals[mid]["total_fee"] += fee_amount

    return {
        "withdrawals_by_merchant": [
            {"merchant_id": mid, **data} for mid, data in merchant_totals.items()
        ]
    }


def process_refunds(refunds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group refunds/autorefunds by merchant using withdrawal fee logic."""
    merchant_totals = defaultdict(lambda: {"count": 0, "total_amount": 0.0, "total_fee": 0.0})

    for r in refunds:
        mid = r.get("merchant_id", "unknown")
        amount = _to_float(r.get("amount", 0))
        fee_amount = _to_float(r.get("fee_amount", 0))
        msa = _to_float(r.get("msa", 0))

        if fee_amount == 0:
            fee_amount = recompute_fee(amount, msa)

        merchant_totals[mid]["merchant_name"] = r.get("merchant_name", mid)
        merchant_totals[mid]["type"] = r.get("type", "refund")
        merchant_totals[mid]["count"] += 1
        merchant_totals[mid]["total_amount"] += amount
        merchant_totals[mid]["total_fee"] += fee_amount

    return {
        "refunds_by_merchant": [
            {"merchant_id": mid, **data} for mid, data in merchant_totals.items()
        ]
    }


def consolidate_fees(tx_result: Dict, withdrawal_result: Dict, refund_result: Dict) -> Dict[str, Any]:
    """Final consolidation of all FEES components."""
    total_tx_fees = sum(m["total_fee"] for m in tx_result["merchant_summary"])
    total_withdrawal_fees = sum(
        m["total_fee"] for m in withdrawal_result.get("withdrawals_by_merchant", [])
    )
    total_refund_fees = sum(
        m["total_fee"] for m in refund_result.get("refunds_by_merchant", [])
    )
    total_fees = round(total_tx_fees + total_withdrawal_fees + total_refund_fees, 6)

    return {
        "merchant_summary": tx_result["merchant_summary"],
        "daily_breakdown": tx_result["daily_breakdown"],
        "withdrawals_summary": withdrawal_result.get("withdrawals_by_merchant", []),
        "refunds_summary": refund_result.get("refunds_by_merchant", []),
        "other_fees_summary": [],  # placeholder for settlements
        "total_fees": total_fees,
        "totals": {
            "total_tx_fees": round(total_tx_fees, 6),
            "total_withdrawal_fees": round(total_withdrawal_fees, 6),
            "total_refund_fees": round(total_refund_fees, 6),
            "total_fees": total_fees,
        },
    }
