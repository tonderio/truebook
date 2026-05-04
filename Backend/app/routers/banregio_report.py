"""
HTTP endpoint for the Banregio Reconciliation Report v2.

Exposes `POST /api/processes/{id}/banregio-report-v2` which:
  1. Validates the process exists and is in completed/reconciled state
  2. Builds the 3-sheet xlsx via `banregio_report_v2.builder`
  3. Persists a copy to `uploads/{process_id}/reports/` for audit history
  4. Returns the file as a streaming download with the spec filename

The endpoint is intentionally `POST` (not `GET`) because it's a costly
generation that writes to disk — convention for "produce + return"
operations in this codebase.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.process import AccountingProcess
from app.models.classification import BanregioMovementClassification
from app.config import settings
from app.services.banregio_report_v2 import builder


router = APIRouter(prefix="/api/processes", tags=["banregio_report_v2"])


@router.post("/{process_id}/banregio-report-v2")
def generate_v2_report(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate and download the v2 Banregio Reconciliation Report.

    Returns the .xlsx file directly (Content-Disposition: attachment) so
    the browser triggers a download. Also persists an audit copy at
    `uploads/{process_id}/reports/{filename}`.
    """
    process = db.query(AccountingProcess).filter_by(id=process_id).first()
    if not process:
        raise HTTPException(status_code=404, detail="Process not found")

    # Allow generation on completed or reconciled runs. Earlier states
    # (running/pending/failed) don't have the data populated.
    if process.status not in ("completed", "reconciled"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Process must be in 'completed' or 'reconciled' status to "
                f"generate the v2 report (current: {process.status})"
            ),
        )

    # Defensive: a process can be in 'completed' status but have an empty
    # BanregioMovementClassification table — happens if files were
    # uploaded/parsed but the pipeline's auto_classify stage didn't run
    # (interrupted run, manually-set status, partial re-run, etc.).
    # Generating a v2 report in this state silently produces a 0%-coverage
    # workbook which is misleading to FinOps. Fail fast with a clear hint.
    cls_count = (
        db.query(BanregioMovementClassification)
        .filter_by(process_id=process_id)
        .count()
    )
    if cls_count == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "Process has no Banregio classifications — pipeline did not "
                "complete the auto-classify stage. Click 'Ejecutar proceso' "
                "to run the full pipeline before generating the v2 report."
            ),
        )

    # Build the workbook → bytes
    try:
        xlsx_bytes, _stats = builder.build_to_bytes(db, process)
    except Exception as exc:  # pragma: no cover — defensive
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {type(exc).__name__}: {exc}",
        )

    filename = builder.default_filename(process)

    # Persist audit copy (best-effort — don't fail the response if disk write fails)
    try:
        base_dir = os.path.abspath(settings.UPLOAD_DIR)
        report_dir = Path(base_dir) / str(process.id) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        with open(report_dir / filename, "wb") as f:
            f.write(xlsx_bytes)
    except Exception:
        pass

    # Stream back to the client as a download
    return Response(
        content=xlsx_bytes,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(xlsx_bytes)),
        },
    )
