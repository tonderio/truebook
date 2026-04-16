import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.process import AccountingProcess
from app.models.result import FeesResult, KushkiResult, BanregioResult, ConciliationResult
from app.models.adjustment import RunAdjustment
from app.models.classification import BanregioMovementClassification
from app.services.aws_settlements import get_status as aws_status
from app.services.auto_classifier import compute_coverage
from app.services.excel_exports import build_fees_export, build_kushki_export, build_banregio_export
from app.services.conciliation_engine import compute_adjusted_delta
from typing import List

router = APIRouter(prefix="/api/results", tags=["results"])


@router.get("/{process_id}/reconciliation-view")
def get_reconciliation_view(
    process_id: int,
    filter: str = "all",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Banregio movements enriched with classification data.
    The core reconciliation view — every movement with its status.
    Filter: 'all', 'reconciled', 'pending'
    """
    banregio = db.query(BanregioResult).filter(
        BanregioResult.process_id == process_id
    ).first()
    if not banregio or not banregio.movements:
        raise HTTPException(status_code=404, detail="No Banregio data found")

    classifications = db.query(BanregioMovementClassification).filter(
        BanregioMovementClassification.process_id == process_id
    ).all()
    cls_map = {c.movement_index: c for c in classifications}

    movements = []
    for idx, mov in enumerate(banregio.movements):
        cls = cls_map.get(idx)
        classification = cls.classification if cls else "unclassified"
        acquirer = cls.acquirer if cls else None
        method = cls.classification_method if cls else None
        is_reconciled = classification != "unclassified"

        if filter == "reconciled" and not is_reconciled:
            continue
        if filter == "pending" and is_reconciled:
            continue

        movements.append({
            "index": idx,
            "date": mov.get("date", ""),
            "description": mov.get("description", ""),
            "credit": float(mov.get("credit", 0) or 0),
            "debit": float(mov.get("debit", 0) or 0),
            "deposit_ref": mov.get("deposit_ref", ""),
            "classification": classification,
            "acquirer": acquirer,
            "is_reconciled": is_reconciled,
            "method": method,
            "notes": cls.notes if cls else None,
        })

    # Summary
    all_cls = [{"classification": c.classification} for c in classifications]
    stats = compute_coverage(all_cls) if all_cls else {
        "total_movements": len(banregio.movements),
        "classified": 0, "unclassified": len(banregio.movements),
        "ignored": 0, "coverage_pct": 0.0, "by_classification": {},
    }
    # Fix total to match actual Banregio count
    stats["total_movements"] = len(banregio.movements)

    return {
        "movements": movements,
        "summary": stats,
        "filter": filter,
        "showing": len(movements),
    }


@router.get("/{process_id}/acquirer-breakdown")
def get_acquirer_breakdown(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Banregio deposits grouped by acquirer, with merchant detail where available.
    """
    classifications = db.query(BanregioMovementClassification).filter(
        BanregioMovementClassification.process_id == process_id
    ).all()

    banregio = db.query(BanregioResult).filter(
        BanregioResult.process_id == process_id
    ).first()
    movements = banregio.movements if banregio else []

    # Group by acquirer
    acquirer_groups = {}
    for cls in classifications:
        if not cls.acquirer:
            continue
        if cls.acquirer not in acquirer_groups:
            acquirer_groups[cls.acquirer] = {
                "name": cls.acquirer,
                "classification": cls.classification,
                "deposits": [],
                "total_amount": 0,
            }
        mov = movements[cls.movement_index] if cls.movement_index < len(movements) else {}
        amount = float(mov.get("credit", 0) or 0)
        acquirer_groups[cls.acquirer]["deposits"].append({
            "index": cls.movement_index,
            "date": mov.get("date", ""),
            "description": mov.get("description", ""),
            "amount": amount,
        })
        acquirer_groups[cls.acquirer]["total_amount"] += amount

    # Add Kushki merchant detail if available
    kushki = db.query(KushkiResult).filter(
        KushkiResult.process_id == process_id
    ).first()
    if kushki and "kushki" in acquirer_groups:
        acquirer_groups["kushki"]["merchants"] = kushki.merchant_detail or []

    # Sort by total amount descending
    acquirers = sorted(
        acquirer_groups.values(),
        key=lambda a: a["total_amount"],
        reverse=True,
    )

    # Non-acquirer classifications summary
    non_acquirer = {}
    for cls in classifications:
        if cls.acquirer:
            continue
        cat = cls.classification
        if cat == "unclassified":
            continue
        if cat not in non_acquirer:
            non_acquirer[cat] = {"name": cat, "count": 0, "total_amount": 0}
        mov = movements[cls.movement_index] if cls.movement_index < len(movements) else {}
        amount = float(mov.get("credit", 0) or 0) - float(mov.get("debit", 0) or 0)
        non_acquirer[cat]["count"] += 1
        non_acquirer[cat]["total_amount"] += amount

    return {
        "acquirers": acquirers,
        "other_categories": sorted(non_acquirer.values(), key=lambda x: -abs(x["total_amount"])),
    }


@router.get("/{process_id}/fees")
def get_fees_result(process_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = db.query(FeesResult).filter(FeesResult.process_id == process_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="FEES result not found")
    return {
        "process_id": process_id,
        "merchant_summary": result.merchant_summary,
        "daily_breakdown": result.daily_breakdown,
        "withdrawals_summary": result.withdrawals_summary,
        "refunds_summary": result.refunds_summary,
        "other_fees_summary": result.other_fees_summary,
        "total_fees": float(result.total_fees) if result.total_fees else 0,
        "created_at": result.created_at,
    }


@router.get("/{process_id}/kushki")
def get_kushki_result(process_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = db.query(KushkiResult).filter(KushkiResult.process_id == process_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Kushki result not found")
    return {
        "process_id": process_id,
        "daily_summary": result.daily_summary,
        "merchant_detail": result.merchant_detail,
        "total_net_deposit": float(result.total_net_deposit) if result.total_net_deposit else 0,
        "created_at": result.created_at,
    }


@router.get("/{process_id}/banregio")
def get_banregio_result(process_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = db.query(BanregioResult).filter(BanregioResult.process_id == process_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Banregio result not found")
    return {
        "process_id": process_id,
        "movements": result.movements,
        "summary": result.summary,
        "created_at": result.created_at,
    }


@router.get("/{process_id}/conciliation/summary")
def get_conciliation_summary(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enriched conciliation summary with delta bruto and delta ajustado.

    For each conciliation type, layers approved adjustments on top of the raw
    delta to compute the adjusted delta. Both values are always returned so
    the frontend can show them side-by-side.
    """
    results = (
        db.query(ConciliationResult)
        .filter(ConciliationResult.process_id == process_id)
        .all()
    )
    if not results:
        raise HTTPException(status_code=404, detail="No conciliation results found")

    # Fetch all approved adjustments for this process
    approved = (
        db.query(RunAdjustment)
        .filter(
            RunAdjustment.process_id == process_id,
            RunAdjustment.status == "approved",
        )
        .all()
    )
    adj_dicts = [
        {
            "id": a.id,
            "adjustment_type": a.adjustment_type,
            "direction": a.direction,
            "amount": float(a.amount),
            "affects": a.affects,
            "conciliation_type": a.conciliation_type,
            "description": a.description,
        }
        for a in approved
    ]

    summary = []
    total_delta_bruto = 0.0
    total_delta_ajustado = 0.0

    for r in results:
        delta_bruto = float(r.total_difference) if r.total_difference else 0
        adjusted = compute_adjusted_delta(
            delta_bruto=delta_bruto,
            adjustments=adj_dicts,
            conciliation_type=r.conciliation_type,
        )

        total_delta_bruto += delta_bruto
        total_delta_ajustado += adjusted["delta_ajustado"]

        summary.append({
            "conciliation_type": r.conciliation_type,
            "total_conciliated": float(r.total_conciliated) if r.total_conciliated else 0,
            "matched_count": len(r.matched) if r.matched else 0,
            "differences_count": len(r.differences) if r.differences else 0,
            "unmatched_kushki_count": len(r.unmatched_kushki) if r.unmatched_kushki else 0,
            "unmatched_banregio_count": len(r.unmatched_banregio) if r.unmatched_banregio else 0,
            **adjusted,
        })

    return {
        "process_id": process_id,
        "conciliations": summary,
        "totals": {
            "delta_bruto": round(total_delta_bruto, 2),
            "delta_ajustado": round(total_delta_ajustado, 2),
            "total_adjustments_applied": sum(
                s["adjustments_count"] for s in summary
            ),
        },
    }


@router.get("/{process_id}/conciliation")
def get_conciliation(process_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    results = (
        db.query(ConciliationResult)
        .filter(ConciliationResult.process_id == process_id)
        .all()
    )
    return [
        {
            "id": r.id,
            "conciliation_type": r.conciliation_type,
            "matched": r.matched,
            "differences": r.differences,
            "unmatched_kushki": r.unmatched_kushki,
            "unmatched_banregio": r.unmatched_banregio,
            "total_conciliated": float(r.total_conciliated) if r.total_conciliated else 0,
            "total_difference": float(r.total_difference) if r.total_difference else 0,
            "created_at": r.created_at,
        }
        for r in results
    ]


@router.get("/aws/status")
def get_aws_status(current_user: User = Depends(get_current_user)):
    return aws_status()


def _xlsx_response(filename: str, content: bytes):
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{process_id}/export/fees")
def export_fees_excel(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    process = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
    if not process:
        raise HTTPException(status_code=404, detail="Process not found")

    fees = db.query(FeesResult).filter(FeesResult.process_id == process_id).first()
    if not fees:
        raise HTTPException(status_code=404, detail="FEES result not found")

    filename, content = build_fees_export(process, fees)
    return _xlsx_response(filename, content)


@router.get("/{process_id}/export/kushki")
def export_kushki_excel(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    process = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
    if not process:
        raise HTTPException(status_code=404, detail="Process not found")

    kushki = db.query(KushkiResult).filter(KushkiResult.process_id == process_id).first()
    if not kushki:
        raise HTTPException(status_code=404, detail="Kushki result not found")

    filename, content = build_kushki_export(process, kushki)
    return _xlsx_response(filename, content)


@router.get("/{process_id}/export/banregio")
def export_banregio_excel(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    process = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
    if not process:
        raise HTTPException(status_code=404, detail="Process not found")

    banregio = db.query(BanregioResult).filter(BanregioResult.process_id == process_id).first()
    if not banregio:
        raise HTTPException(status_code=404, detail="Banregio result not found")

    kushki = db.query(KushkiResult).filter(KushkiResult.process_id == process_id).first()
    conciliations = (
        db.query(ConciliationResult)
        .filter(ConciliationResult.process_id == process_id)
        .all()
    )

    filename, content = build_banregio_export(process, banregio, kushki, conciliations)
    return _xlsx_response(filename, content)
