"""
Banregio movement classifications CRUD + auto-classification + coverage stats.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.process import AccountingProcess
from app.models.result import BanregioResult
from app.models.classification import BanregioMovementClassification
from app.schemas.classification import ClassificationCreate, ClassificationOut, CoverageStats, BulkClassifyRequest
from app.services.auto_classifier import auto_classify_all, compute_coverage

router = APIRouter(prefix="/api/classifications", tags=["classifications"])


@router.get("/{process_id}", response_model=List[ClassificationOut])
def list_classifications(
    process_id: int,
    classification: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all classifications for a process, optionally filtered."""
    query = db.query(BanregioMovementClassification).filter(
        BanregioMovementClassification.process_id == process_id
    )
    if classification:
        query = query.filter(
            BanregioMovementClassification.classification == classification
        )
    return query.order_by(BanregioMovementClassification.movement_index).all()


@router.get("/{process_id}/coverage", response_model=CoverageStats)
def get_coverage(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get Banregio coverage statistics for a process."""
    classifications = (
        db.query(BanregioMovementClassification)
        .filter(BanregioMovementClassification.process_id == process_id)
        .all()
    )
    if not classifications:
        # Check if Banregio data exists but hasn't been classified yet
        banregio = db.query(BanregioResult).filter(
            BanregioResult.process_id == process_id
        ).first()
        if banregio and banregio.movements:
            return CoverageStats(
                total_movements=len(banregio.movements),
                classified=0,
                unclassified=len(banregio.movements),
                ignored=0,
                coverage_pct=0.0,
                by_classification={"unclassified": len(banregio.movements)},
            )
        return CoverageStats(
            total_movements=0, classified=0, unclassified=0,
            ignored=0, coverage_pct=0.0, by_classification={},
        )

    data = [
        {"classification": c.classification}
        for c in classifications
    ]
    stats = compute_coverage(data)
    return CoverageStats(**stats)


@router.post("/{process_id}/auto")
def auto_classify(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run auto-classification on all Banregio movements for a process."""
    proc = db.query(AccountingProcess).filter(
        AccountingProcess.id == process_id
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    if proc.status not in ("completed", "reconciled"):
        raise HTTPException(
            status_code=400,
            detail="Process must be completed before classification",
        )

    banregio = db.query(BanregioResult).filter(
        BanregioResult.process_id == process_id
    ).first()
    if not banregio or not banregio.movements:
        raise HTTPException(status_code=404, detail="No Banregio data found")

    # Run auto-classification
    classifications = auto_classify_all(banregio.movements)

    # Upsert classifications (keep existing manual ones, only update unclassified)
    created = 0
    skipped = 0
    for cls_data in classifications:
        existing = (
            db.query(BanregioMovementClassification)
            .filter(
                BanregioMovementClassification.process_id == process_id,
                BanregioMovementClassification.movement_index == cls_data["movement_index"],
            )
            .first()
        )
        if existing:
            # Only overwrite if current classification is 'unclassified'
            if existing.classification == "unclassified" and cls_data["classification"] != "unclassified":
                existing.classification = cls_data["classification"]
                existing.acquirer = cls_data["acquirer"]
                existing.classification_method = "auto"
                created += 1
            else:
                skipped += 1
        else:
            db.add(BanregioMovementClassification(
                process_id=process_id,
                classified_by=current_user.id,
                **cls_data,
            ))
            created += 1

    db.commit()

    # Update coverage on process
    all_cls = (
        db.query(BanregioMovementClassification)
        .filter(BanregioMovementClassification.process_id == process_id)
        .all()
    )
    data = [{"classification": c.classification} for c in all_cls]
    stats = compute_coverage(data)
    proc.coverage_pct = stats["coverage_pct"]
    db.commit()

    return {
        "message": f"Auto-classification complete: {created} classified, {skipped} skipped",
        "coverage": stats,
    }


@router.put("/{process_id}/{movement_index}")
def classify_movement(
    process_id: int,
    movement_index: int,
    body: ClassificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually classify or reclassify a single Banregio movement."""
    proc = db.query(AccountingProcess).filter(
        AccountingProcess.id == process_id
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")

    # Validate movement index exists
    banregio = db.query(BanregioResult).filter(
        BanregioResult.process_id == process_id
    ).first()
    if not banregio or not banregio.movements:
        raise HTTPException(status_code=404, detail="No Banregio data found")
    if movement_index < 0 or movement_index >= len(banregio.movements):
        raise HTTPException(status_code=400, detail="Invalid movement index")

    # Validate ignored requires notes
    if body.classification == "ignored" and not body.notes:
        raise HTTPException(
            status_code=400,
            detail="Ignored classification requires notes (reason)",
        )

    mov = banregio.movements[movement_index]

    existing = (
        db.query(BanregioMovementClassification)
        .filter(
            BanregioMovementClassification.process_id == process_id,
            BanregioMovementClassification.movement_index == movement_index,
        )
        .first()
    )

    if existing:
        existing.classification = body.classification
        existing.acquirer = body.acquirer
        existing.notes = body.notes
        existing.classified_by = current_user.id
        existing.classification_method = "manual"
    else:
        credit = mov.get("credit") or 0
        debit = mov.get("debit") or 0
        db.add(BanregioMovementClassification(
            process_id=process_id,
            movement_index=movement_index,
            movement_date=mov.get("date", ""),
            movement_description=mov.get("description", ""),
            movement_amount=credit if credit else -debit,
            movement_type="abono" if credit else "cargo",
            classification=body.classification,
            acquirer=body.acquirer,
            notes=body.notes,
            classified_by=current_user.id,
            classification_method="manual",
        ))

    db.commit()

    # Update coverage on process
    all_cls = (
        db.query(BanregioMovementClassification)
        .filter(BanregioMovementClassification.process_id == process_id)
        .all()
    )
    data = [{"classification": c.classification} for c in all_cls]
    stats = compute_coverage(data)
    proc.coverage_pct = stats["coverage_pct"]
    db.commit()

    return {"message": "Classification updated", "coverage": stats}


@router.post("/{process_id}/bulk")
def bulk_classify(
    process_id: int,
    body: BulkClassifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk classify multiple movements at once."""
    indices = body.movement_indices
    classification = body.classification
    acquirer = body.acquirer
    notes = body.notes

    if not indices:
        raise HTTPException(status_code=400, detail="movement_indices must not be empty")

    if classification == "ignored" and not notes:
        raise HTTPException(status_code=400, detail="Ignored classification requires notes")

    proc = db.query(AccountingProcess).filter(
        AccountingProcess.id == process_id
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")

    banregio = db.query(BanregioResult).filter(
        BanregioResult.process_id == process_id
    ).first()
    if not banregio or not banregio.movements:
        raise HTTPException(status_code=404, detail="No Banregio data found")

    updated = 0
    for idx in indices:
        if idx < 0 or idx >= len(banregio.movements):
            continue

        mov = banregio.movements[idx]
        existing = (
            db.query(BanregioMovementClassification)
            .filter(
                BanregioMovementClassification.process_id == process_id,
                BanregioMovementClassification.movement_index == idx,
            )
            .first()
        )

        credit = mov.get("credit") or 0
        debit = mov.get("debit") or 0

        if existing:
            existing.classification = classification
            existing.acquirer = acquirer
            existing.notes = notes
            existing.classified_by = current_user.id
            existing.classification_method = "manual"
        else:
            db.add(BanregioMovementClassification(
                process_id=process_id,
                movement_index=idx,
                movement_date=mov.get("date", ""),
                movement_description=mov.get("description", ""),
                movement_amount=credit if credit else -debit,
                movement_type="abono" if credit else "cargo",
                classification=classification,
                acquirer=acquirer,
                notes=notes,
                classified_by=current_user.id,
                classification_method="manual",
            ))
        updated += 1

    db.commit()

    # Update coverage
    all_cls = (
        db.query(BanregioMovementClassification)
        .filter(BanregioMovementClassification.process_id == process_id)
        .all()
    )
    data = [{"classification": c.classification} for c in all_cls]
    stats = compute_coverage(data)
    proc.coverage_pct = stats["coverage_pct"]
    db.commit()

    return {"message": f"{updated} movements classified", "coverage": stats}
