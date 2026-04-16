"""
Warren AI Agent — API endpoints for intelligent movement classification.

Warren analyzes unclassified Banregio movements using Claude and suggests
labels with confidence scores. The operator reviews and accepts/rejects.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.process import AccountingProcess
from app.models.result import BanregioResult
from app.models.classification import BanregioMovementClassification
from app.services.warren_agent import classify_with_warren_sync, VALID_LABELS
from app.services.auto_classifier import compute_coverage
from app.schemas.warren import ApplyWarrenRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/warren", tags=["warren"])


@router.post("/{process_id}/investigate")
def investigate_unclassified(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ask Warren to analyze unclassified Banregio movements and suggest labels.

    Only processes unclassified movements — already-classified ones are skipped.
    Returns suggestions with confidence scores for human review.
    """
    proc = db.query(AccountingProcess).filter(
        AccountingProcess.id == process_id
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    if proc.status not in ("completed", "reconciled"):
        raise HTTPException(status_code=400, detail="Process must be completed first")

    banregio = db.query(BanregioResult).filter(
        BanregioResult.process_id == process_id
    ).first()
    if not banregio or not banregio.movements:
        raise HTTPException(status_code=404, detail="No Banregio data found")

    # Get current classifications
    classifications = db.query(BanregioMovementClassification).filter(
        BanregioMovementClassification.process_id == process_id
    ).all()
    classified_indices = {c.movement_index: c.classification for c in classifications}

    # Find unclassified movements
    unclassified = []
    for idx, mov in enumerate(banregio.movements):
        cls = classified_indices.get(idx, "unclassified")
        if cls == "unclassified":
            credit = mov.get("credit") or 0
            debit = mov.get("debit") or 0
            unclassified.append({
                "movement_index": idx,
                "movement_date": mov.get("date", ""),
                "movement_description": mov.get("description", ""),
                "reference": mov.get("deposit_ref", "") or mov.get("reference", ""),
                "movement_amount": credit if credit else -debit,
                "movement_type": "abono" if credit else "cargo",
            })

    if not unclassified:
        return {
            "message": "No unclassified movements found — nothing for Warren to investigate",
            "unclassified_count": 0,
            "suggestions": [],
        }

    # Call Warren
    suggestions = classify_with_warren_sync(unclassified)

    return {
        "unclassified_count": len(unclassified),
        "suggestions": suggestions,
        "message": f"Warren analyzed {len(unclassified)} unclassified movement(s)",
    }


@router.post("/{process_id}/apply")
def apply_warren_suggestions(
    process_id: int,
    body: ApplyWarrenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Apply Warren's suggestions to classify movements."""
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

    min_confidence = body.min_confidence

    applied = 0
    skipped = 0

    for s in body.suggestions:
        idx = s.movement_index
        label = s.label or s.suggested_label
        confidence = s.confidence

        if label is None:
            skipped += 1
            continue

        if label not in VALID_LABELS:
            skipped += 1
            continue

        if confidence < min_confidence:
            skipped += 1
            continue

        if idx < 0 or idx >= len(banregio.movements):
            skipped += 1
            continue

        mov = banregio.movements[idx]
        credit = mov.get("credit") or 0
        debit = mov.get("debit") or 0

        # Determine acquirer from label
        acquirer = None
        if label.endswith("_acquirer"):
            acquirer = label.replace("_acquirer", "")

        existing = db.query(BanregioMovementClassification).filter(
            BanregioMovementClassification.process_id == process_id,
            BanregioMovementClassification.movement_index == idx,
        ).first()

        reasoning = s.reasoning or ""
        notes = f"Warren AI (confidence: {confidence:.0%}): {reasoning}"

        if existing:
            if existing.classification != "unclassified":
                skipped += 1
                continue
            existing.classification = label
            existing.acquirer = acquirer
            existing.classification_method = "warren_ai"
            existing.notes = notes
            existing.classified_by = current_user.id
        else:
            db.add(BanregioMovementClassification(
                process_id=process_id,
                movement_index=idx,
                movement_date=mov.get("date", ""),
                movement_description=mov.get("description", ""),
                movement_amount=credit if credit else -debit,
                movement_type="abono" if credit else "cargo",
                classification=label,
                acquirer=acquirer,
                classification_method="warren_ai",
                notes=notes,
                classified_by=current_user.id,
            ))

        applied += 1

    db.commit()

    # Update coverage
    all_cls = db.query(BanregioMovementClassification).filter(
        BanregioMovementClassification.process_id == process_id
    ).all()
    stats = compute_coverage([{"classification": c.classification} for c in all_cls])
    proc.coverage_pct = stats["coverage_pct"]
    db.commit()

    return {
        "applied": applied,
        "skipped": skipped,
        "coverage": stats,
    }


@router.get("/{process_id}/labels")
def get_label_taxonomy(
    process_id: int = None,
    current_user: User = Depends(get_current_user),
):
    """Return the full label taxonomy with descriptions for the UI."""
    from app.services.warren_agent import LABEL_DESCRIPTIONS
    return {
        "labels": [
            {"name": name, "description": desc}
            for name, desc in LABEL_DESCRIPTIONS.items()
        ],
    }
