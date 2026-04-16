"""
Manual adjustments CRUD with two-eye approval workflow.

Adjustments allow FinOps managers to explain deltas without modifying
the original imported data. Only APPROVED adjustments affect the final
reconciliation delta.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.process import AccountingProcess
from app.models.adjustment import RunAdjustment
from app.schemas.adjustment import AdjustmentCreate, AdjustmentReview, AdjustmentOut

router = APIRouter(prefix="/api/adjustments", tags=["adjustments"])


# ── Summary (static sub-path FIRST to avoid route shadowing) ───────────

@router.get("/{process_id}/summary")
def adjustment_summary(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get adjustment summary for a process: counts by status, total approved amount."""
    adjustments = (
        db.query(RunAdjustment)
        .filter(RunAdjustment.process_id == process_id)
        .all()
    )

    by_status = {"pending": 0, "approved": 0, "rejected": 0}
    total_approved_add = 0
    total_approved_subtract = 0

    for adj in adjustments:
        by_status[adj.status] = by_status.get(adj.status, 0) + 1
        if adj.status == "approved":
            if adj.direction == "ADD":
                total_approved_add += float(adj.amount)
            elif adj.direction == "SUBTRACT":
                total_approved_subtract += float(adj.amount)

    return {
        "total": len(adjustments),
        "by_status": by_status,
        "total_approved_add": round(total_approved_add, 2),
        "total_approved_subtract": round(total_approved_subtract, 2),
        "net_adjustment": round(total_approved_add - total_approved_subtract, 2),
        "has_pending": by_status["pending"] > 0,
    }


# ── CRUD ───────────────────────────────────────────────────────────────

@router.post("/{process_id}", response_model=AdjustmentOut)
def create_adjustment(
    process_id: int,
    body: AdjustmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new adjustment for a process. Requires completed or reconciled status."""
    proc = db.query(AccountingProcess).filter(
        AccountingProcess.id == process_id
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    if proc.status not in ("completed", "reconciled"):
        raise HTTPException(
            status_code=400,
            detail="Adjustments only allowed on completed or reconciled processes",
        )

    adj = RunAdjustment(
        process_id=process_id,
        adjustment_type=body.adjustment_type,
        direction=body.direction,
        amount=body.amount,
        currency=body.currency,
        affects=body.affects,
        conciliation_type=body.conciliation_type,
        merchant_name=body.merchant_name,
        adjustment_date=body.adjustment_date,
        description=body.description,
        evidence_url=body.evidence_url,
        created_by=current_user.id,
        status="pending",
    )
    db.add(adj)
    db.commit()
    db.refresh(adj)
    return adj


@router.get("/{process_id}", response_model=List[AdjustmentOut])
def list_adjustments(
    process_id: int,
    status: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all adjustments for a process, optionally filtered by status."""
    query = db.query(RunAdjustment).filter(
        RunAdjustment.process_id == process_id
    )
    if status:
        query = query.filter(RunAdjustment.status == status)
    return query.order_by(RunAdjustment.created_at.desc()).all()


# ── Approval workflow ──────────────────────────────────────────────────

@router.put("/{adjustment_id}/approve", response_model=AdjustmentOut)
def approve_adjustment(
    adjustment_id: int,
    body: AdjustmentReview = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Approve an adjustment. Two-eye rule: reviewer must be different from creator.
    """
    adj = db.query(RunAdjustment).filter(RunAdjustment.id == adjustment_id).first()
    if not adj:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    if adj.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending adjustments can be approved")

    # Two-eye rule enforcement
    if adj.created_by == current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Two-eye rule: you cannot approve your own adjustment. "
                   "A different user must review and approve.",
        )

    adj.status = "approved"
    adj.reviewed_by = current_user.id
    adj.reviewed_at = datetime.now(timezone.utc)
    if body and body.review_notes:
        adj.review_notes = body.review_notes
    db.commit()
    db.refresh(adj)
    return adj


@router.put("/{adjustment_id}/reject", response_model=AdjustmentOut)
def reject_adjustment(
    adjustment_id: int,
    body: AdjustmentReview = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reject an adjustment. Two-eye rule: reviewer must be different from creator.
    """
    adj = db.query(RunAdjustment).filter(RunAdjustment.id == adjustment_id).first()
    if not adj:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    if adj.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending adjustments can be rejected")

    # Two-eye rule enforcement (same as approve — creator cannot self-reject)
    if adj.created_by == current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Two-eye rule: you cannot reject your own adjustment. "
                   "A different user must review and reject.",
        )

    adj.status = "rejected"
    adj.reviewed_by = current_user.id
    adj.reviewed_at = datetime.now(timezone.utc)
    if body and body.review_notes:
        adj.review_notes = body.review_notes
    db.commit()
    db.refresh(adj)
    return adj


@router.delete("/{adjustment_id}")
def delete_adjustment(
    adjustment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an adjustment. Only the creator can delete, and only while pending."""
    adj = db.query(RunAdjustment).filter(RunAdjustment.id == adjustment_id).first()
    if not adj:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    if adj.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending adjustments can be deleted")
    if adj.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only the creator can delete a pending adjustment")

    db.delete(adj)
    db.commit()
    return {"message": "Adjustment deleted"}
