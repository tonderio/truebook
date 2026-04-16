"""
Bitso manual conciliation: upload reports, find candidates, confirm matches.

When a match is confirmed, the Banregio movement is auto-classified as 'bitso'
and coverage increases. If the match has a non-zero delta, a MANUAL_BITSO
adjustment suggestion is returned.
"""
import os
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.config import settings
from app.core.deps import get_current_user
from app.models.user import User
from app.models.process import AccountingProcess
from app.models.result import BanregioResult
from app.models.classification import BanregioMovementClassification
from app.models.bitso import BitsoReport, BitsoReportLine, BitsoBanregioMatch
from app.models.alert import ReconciliationConfig
from app.schemas.bitso import (
    BitsoUploadResponse, BitsoReportLineOut, BitsoCandidate,
    BitsoMatchRequest, BitsoMatchOut, BitsoSummary,
)
from app.services.bitso_parser import parse_bitso
from app.services.bitso_matcher import find_all_candidates, build_adjustment_suggestion
from app.services.auto_classifier import compute_coverage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bitso", tags=["bitso"])


def _get_config_float(db: Session, key: str, default: float) -> float:
    config = db.query(ReconciliationConfig).filter(
        ReconciliationConfig.config_key == key
    ).first()
    if config:
        try:
            return float(config.config_value)
        except (ValueError, TypeError):
            pass
    return default


def _get_config_int(db: Session, key: str, default: int) -> int:
    config = db.query(ReconciliationConfig).filter(
        ReconciliationConfig.config_key == key
    ).first()
    if config:
        try:
            return int(config.config_value)
        except (ValueError, TypeError):
            pass
    return default


# ── Upload + Parse ─────────────────────────────────────────────────────

@router.post("/{process_id}/upload", response_model=BitsoUploadResponse)
async def upload_bitso_report(
    process_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload and parse a Bitso settlement report (CSV or Excel)."""
    proc = db.query(AccountingProcess).filter(
        AccountingProcess.id == process_id
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")

    # Read and store file
    content = await file.read()
    upload_dir = os.path.join(os.path.abspath(settings.UPLOAD_DIR), str(process_id))
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    stored_name = f"bitso_{uuid.uuid4().hex}{ext}"
    stored_path = os.path.join(upload_dir, stored_name)
    with open(stored_path, "wb") as f:
        f.write(content)

    # Register file in uploaded_files
    from app.models.file import UploadedFile
    file_record = UploadedFile(
        process_id=process_id,
        file_type="bitso",
        original_name=file.filename,
        stored_path=stored_path,
        file_size=len(content),
        status="uploaded",
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)

    # Parse
    try:
        parsed = parse_bitso(content, file.filename)
    except Exception as e:
        file_record.status = "error"
        db.commit()
        raise HTTPException(status_code=400, detail=f"Error parsing Bitso file: {e}")

    file_record.status = "parsed"

    # Delete previous Bitso report for this process (idempotent re-upload)
    # First, revert any Banregio classifications set to "bitso" by previous matches
    old_matches = db.query(BitsoBanregioMatch).filter(
        BitsoBanregioMatch.process_id == process_id
    ).all()
    for m in old_matches:
        cls = db.query(BanregioMovementClassification).filter(
            BanregioMovementClassification.process_id == process_id,
            BanregioMovementClassification.movement_index == m.banregio_movement_index,
            BanregioMovementClassification.classification == "bitso",
        ).first()
        if cls:
            cls.classification = "unclassified"
            cls.acquirer = None
            cls.notes = "Revertido por re-carga de reporte Bitso"

    # Delete matches, lines, and reports
    db.query(BitsoBanregioMatch).filter(
        BitsoBanregioMatch.process_id == process_id
    ).delete()
    old_reports = db.query(BitsoReport).filter(
        BitsoReport.process_id == process_id
    ).all()
    for old in old_reports:
        db.query(BitsoReportLine).filter(BitsoReportLine.report_id == old.id).delete()
    db.query(BitsoReport).filter(BitsoReport.process_id == process_id).delete()
    db.commit()

    # Update coverage after reverting classifications
    proc = db.query(AccountingProcess).filter(
        AccountingProcess.id == process_id
    ).first()
    if proc:
        all_cls = db.query(BanregioMovementClassification).filter(
            BanregioMovementClassification.process_id == process_id
        ).all()
        if all_cls:
            stats = compute_coverage([{"classification": c.classification} for c in all_cls])
            proc.coverage_pct = stats["coverage_pct"]
            db.commit()

    # Create report
    report = BitsoReport(
        process_id=process_id,
        file_id=file_record.id,
        period_start=parsed["period_start"],
        period_end=parsed["period_end"],
        total_rows=len(parsed["lines"]),
        total_amount=parsed["total_amount"],
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # Create lines
    for line in parsed["lines"]:
        db.add(BitsoReportLine(
            report_id=report.id,
            line_index=line["line_index"],
            txn_date=line["txn_date"],
            txn_id=line.get("txn_id"),
            merchant_name=line.get("merchant_name"),
            gross_amount=line["gross_amount"],
            fee_amount=line["fee_amount"],
            net_amount=line["net_amount"],
            description=line.get("description"),
            status=line.get("status"),
            raw_row=line.get("raw_row"),
        ))
    db.commit()

    return BitsoUploadResponse(
        report_id=report.id,
        total_rows=len(parsed["lines"]),
        total_amount=parsed["total_amount"],
        period_start=parsed["period_start"],
        period_end=parsed["period_end"],
    )


# ── Report Lines ───────────────────────────────────────────────────────

@router.get("/{process_id}/report")
def get_bitso_report(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get parsed Bitso report lines with match status."""
    report = db.query(BitsoReport).filter(
        BitsoReport.process_id == process_id
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="No Bitso report found for this process")

    lines = db.query(BitsoReportLine).filter(
        BitsoReportLine.report_id == report.id
    ).order_by(BitsoReportLine.line_index).all()

    # Get matched line IDs
    matches = db.query(BitsoBanregioMatch.bitso_line_id).filter(
        BitsoBanregioMatch.process_id == process_id
    ).all()
    matched_ids = {m[0] for m in matches}

    return {
        "report_id": report.id,
        "total_rows": report.total_rows,
        "total_amount": float(report.total_amount) if report.total_amount else 0,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "lines": [
            {
                "id": l.id,
                "line_index": l.line_index,
                "txn_date": l.txn_date,
                "txn_id": l.txn_id,
                "merchant_name": l.merchant_name,
                "gross_amount": float(l.gross_amount) if l.gross_amount else 0,
                "fee_amount": float(l.fee_amount) if l.fee_amount else 0,
                "net_amount": float(l.net_amount) if l.net_amount else 0,
                "description": l.description,
                "is_matched": l.id in matched_ids,
            }
            for l in lines
        ],
    }


# ── Candidates ─────────────────────────────────────────────────────────

@router.get("/{process_id}/candidates")
def get_candidates(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Find candidate Banregio matches for all unmatched Bitso lines."""
    report = db.query(BitsoReport).filter(
        BitsoReport.process_id == process_id
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="No Bitso report found")

    banregio = db.query(BanregioResult).filter(
        BanregioResult.process_id == process_id
    ).first()
    if not banregio or not banregio.movements:
        raise HTTPException(status_code=404, detail="No Banregio data found")

    # Get unmatched Bitso lines
    matched_line_ids = {
        m[0] for m in
        db.query(BitsoBanregioMatch.bitso_line_id)
        .filter(BitsoBanregioMatch.process_id == process_id)
        .all()
    }
    matched_movement_indices = {
        m[0] for m in
        db.query(BitsoBanregioMatch.banregio_movement_index)
        .filter(BitsoBanregioMatch.process_id == process_id)
        .all()
    }

    lines = db.query(BitsoReportLine).filter(
        BitsoReportLine.report_id == report.id
    ).all()
    unmatched_lines = [l for l in lines if l.id not in matched_line_ids]

    # Get classifications
    classifications_rows = db.query(BanregioMovementClassification).filter(
        BanregioMovementClassification.process_id == process_id
    ).all()
    existing_cls = {c.movement_index: c.classification for c in classifications_rows}

    # Config
    tolerance_amount = _get_config_float(db, "bitso_match_tolerance_amount", 1.00)
    tolerance_days = _get_config_int(db, "bitso_match_window_days", 3)

    # Build line dicts for matcher
    line_dicts = [
        {
            "id": l.id,
            "txn_date": l.txn_date,
            "net_amount": float(l.net_amount) if l.net_amount else 0,
            "gross_amount": float(l.gross_amount) if l.gross_amount else 0,
            "merchant_name": l.merchant_name,
        }
        for l in unmatched_lines
    ]

    all_candidates = find_all_candidates(
        bitso_lines=line_dicts,
        banregio_movements=banregio.movements,
        existing_classifications=existing_cls,
        existing_matches=matched_movement_indices,
        tolerance_amount=tolerance_amount,
        tolerance_days=tolerance_days,
    )

    return {
        "tolerance_amount": tolerance_amount,
        "tolerance_days": tolerance_days,
        "unmatched_lines": len(unmatched_lines),
        "candidates": {
            str(line_id): candidates
            for line_id, candidates in all_candidates.items()
        },
    }


# ── Match / Unmatch ────────────────────────────────────────────────────

@router.post("/{process_id}/match", response_model=BitsoMatchOut)
def confirm_match(
    process_id: int,
    body: BitsoMatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm a Bitso-Banregio match. Auto-classifies the movement as 'bitso'."""
    # Validate Bitso line exists AND belongs to this process
    bitso_line = (
        db.query(BitsoReportLine)
        .join(BitsoReport, BitsoReportLine.report_id == BitsoReport.id)
        .filter(
            BitsoReportLine.id == body.bitso_line_id,
            BitsoReport.process_id == process_id,
        )
        .first()
    )
    if not bitso_line:
        raise HTTPException(
            status_code=404,
            detail="Bitso line not found or does not belong to this process",
        )

    # Validate Banregio movement exists
    banregio = db.query(BanregioResult).filter(
        BanregioResult.process_id == process_id
    ).first()
    if not banregio or not banregio.movements:
        raise HTTPException(status_code=404, detail="No Banregio data found")
    if body.banregio_movement_index < 0 or body.banregio_movement_index >= len(banregio.movements):
        raise HTTPException(status_code=400, detail="Invalid Banregio movement index")

    # Check not already matched
    existing = db.query(BitsoBanregioMatch).filter(
        BitsoBanregioMatch.process_id == process_id,
        BitsoBanregioMatch.bitso_line_id == body.bitso_line_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bitso line already matched")

    existing_mov = db.query(BitsoBanregioMatch).filter(
        BitsoBanregioMatch.process_id == process_id,
        BitsoBanregioMatch.banregio_movement_index == body.banregio_movement_index,
    ).first()
    if existing_mov:
        raise HTTPException(status_code=400, detail="Banregio movement already matched to another Bitso line")

    # Compute amounts
    bitso_amount = float(bitso_line.net_amount) if bitso_line.net_amount else 0
    mov = banregio.movements[body.banregio_movement_index]
    banregio_amount = float(mov.get("credit", 0) or 0)
    delta = round(banregio_amount - bitso_amount, 2)

    # Create match
    match = BitsoBanregioMatch(
        process_id=process_id,
        bitso_line_id=body.bitso_line_id,
        banregio_movement_index=body.banregio_movement_index,
        bitso_amount=bitso_amount,
        banregio_amount=banregio_amount,
        delta=delta,
        match_method="manual",
        matched_by=current_user.id,
        notes=body.notes,
    )
    db.add(match)
    db.commit()
    db.refresh(match)

    # Auto-classify the Banregio movement as 'bitso'
    proc = db.query(AccountingProcess).filter(
        AccountingProcess.id == process_id
    ).first()

    existing_cls = db.query(BanregioMovementClassification).filter(
        BanregioMovementClassification.process_id == process_id,
        BanregioMovementClassification.movement_index == body.banregio_movement_index,
    ).first()

    if existing_cls:
        existing_cls.classification = "bitso"
        existing_cls.acquirer = "bitso"
        existing_cls.classification_method = "auto"
        existing_cls.notes = f"Cruce Bitso confirmado (match_id={match.id})"
    else:
        db.add(BanregioMovementClassification(
            process_id=process_id,
            movement_index=body.banregio_movement_index,
            movement_date=mov.get("date", ""),
            movement_description=mov.get("description", ""),
            movement_amount=banregio_amount,
            movement_type="abono",
            classification="bitso",
            acquirer="bitso",
            classification_method="auto",
            notes=f"Cruce Bitso confirmado (match_id={match.id})",
            classified_by=current_user.id,
        ))
    db.commit()

    # Update coverage on process
    if proc:
        all_cls = db.query(BanregioMovementClassification).filter(
            BanregioMovementClassification.process_id == process_id
        ).all()
        stats = compute_coverage([{"classification": c.classification} for c in all_cls])
        proc.coverage_pct = stats["coverage_pct"]
        db.commit()

    # Build adjustment suggestion if delta exceeds configured tolerance
    tolerance_amount = _get_config_float(db, "bitso_match_tolerance_amount", 1.00)
    suggested = build_adjustment_suggestion(
        bitso_amount=bitso_amount,
        banregio_amount=banregio_amount,
        process_id=process_id,
        merchant_name=bitso_line.merchant_name,
        match_date=bitso_line.txn_date,
        tolerance_amount=tolerance_amount,
    )

    return BitsoMatchOut(
        id=match.id,
        bitso_line_id=match.bitso_line_id,
        banregio_movement_index=match.banregio_movement_index,
        bitso_amount=float(match.bitso_amount),
        banregio_amount=float(match.banregio_amount),
        delta=float(match.delta),
        match_method=match.match_method,
        matched_by=match.matched_by,
        matched_at=match.matched_at,
        notes=match.notes,
        suggested_adjustment=suggested,
    )


@router.delete("/{process_id}/match/{match_id}")
def unmatch(
    process_id: int,
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a Bitso-Banregio match. Reverts classification to 'unclassified'."""
    match = db.query(BitsoBanregioMatch).filter(
        BitsoBanregioMatch.id == match_id,
        BitsoBanregioMatch.process_id == process_id,
    ).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    movement_index = match.banregio_movement_index

    # Delete the match
    db.delete(match)
    db.commit()

    # Revert classification to unclassified
    cls = db.query(BanregioMovementClassification).filter(
        BanregioMovementClassification.process_id == process_id,
        BanregioMovementClassification.movement_index == movement_index,
    ).first()
    if cls and cls.classification == "bitso":
        cls.classification = "unclassified"
        cls.acquirer = None
        cls.classification_method = "manual"
        cls.notes = "Cruce Bitso deshecho"
        db.commit()

    # Update coverage
    proc = db.query(AccountingProcess).filter(
        AccountingProcess.id == process_id
    ).first()
    if proc:
        all_cls = db.query(BanregioMovementClassification).filter(
            BanregioMovementClassification.process_id == process_id
        ).all()
        stats = compute_coverage([{"classification": c.classification} for c in all_cls])
        proc.coverage_pct = stats["coverage_pct"]
        db.commit()

    return {"message": "Match removed, classification reverted to unclassified"}


# ── Summary ────────────────────────────────────────────────────────────

@router.get("/{process_id}/summary", response_model=BitsoSummary)
def get_bitso_summary(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get Bitso matching progress summary."""
    report = db.query(BitsoReport).filter(
        BitsoReport.process_id == process_id
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="No Bitso report found")

    total_lines = db.query(BitsoReportLine).filter(
        BitsoReportLine.report_id == report.id
    ).count()

    matches = db.query(BitsoBanregioMatch).filter(
        BitsoBanregioMatch.process_id == process_id
    ).all()

    matched_count = len(matches)
    total_bitso = sum(float(m.bitso_amount) for m in matches)
    total_banregio = sum(float(m.banregio_amount) for m in matches)
    total_delta = sum(float(m.delta) for m in matches)

    return BitsoSummary(
        total_lines=total_lines,
        matched=matched_count,
        unmatched=total_lines - matched_count,
        total_bitso_amount=round(total_bitso, 2),
        total_banregio_matched=round(total_banregio, 2),
        total_delta=round(total_delta, 2),
    )
