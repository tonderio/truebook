import logging
import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.config import settings
from app.core.deps import get_current_user
from app.models.user import User
from app.models.process import AccountingProcess, ProcessLog
from app.models.result import FeesResult, KushkiResult, BanregioResult, ConciliationResult
from app.models.file import UploadedFile
from app.models.adjustment import RunAdjustment
from app.models.classification import BanregioMovementClassification
from app.schemas.process import ProcessCreate, ProcessOut, ProcessProgress, ProcessLogOut
from app.services import mongo_extractor, fees_processor, conciliation_engine, kushki_sftp
from app.services.auto_classifier import auto_classify_all, compute_coverage
from app.services import alert_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/processes", tags=["processes"])


def _log(db: Session, process_id: int, stage: str, msg: str, level: str = "info"):
    db.add(ProcessLog(process_id=process_id, stage=stage, level=level, message=msg))
    db.commit()


def _set_stage(db: Session, process: AccountingProcess, stage: str, progress: int):
    process.current_stage = stage
    process.progress = progress
    db.commit()


@router.get("/config")
def get_config(_: User = Depends(get_current_user)):
    return {"kushki_sftp_enabled": settings.KUSHKI_SFTP_ENABLED and kushki_sftp.is_configured()}


@router.post("/", response_model=ProcessOut)
def create_process(
    body: ProcessCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proc = AccountingProcess(
        name=body.name,
        period_year=body.period_year,
        period_month=body.period_month,
        bank_account=body.bank_account,
        acquirers=body.acquirers,
        created_by=current_user.id,
    )
    db.add(proc)
    db.commit()
    db.refresh(proc)
    return proc


def _attach_has_fees_file(proc: AccountingProcess, has_fees: bool) -> ProcessOut:
    """Build a ProcessOut from an AccountingProcess and set has_fees_file.

    Pydantic's from_attributes mode pulls field values from the ORM
    instance; we then set the computed has_fees_file flag (which doesn't
    exist as a column on the model). Used by list / get endpoints below.
    """
    out = ProcessOut.model_validate(proc)
    out.has_fees_file = has_fees
    return out


@router.get("/", response_model=List[ProcessOut])
def list_processes(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    procs = db.query(AccountingProcess).order_by(AccountingProcess.created_at.desc()).all()
    # Pull all process_ids that have a FEES file in one query (no N+1)
    fees_pids = {
        pid for (pid,) in db.query(UploadedFile.process_id)
        .filter(UploadedFile.file_type == "fees")
        .distinct()
    }
    return [_attach_has_fees_file(p, p.id in fees_pids) for p in procs]


@router.get("/{process_id}", response_model=ProcessOut)
def get_process(process_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    proc = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    has_fees = (
        db.query(UploadedFile.id)
        .filter(
            UploadedFile.process_id == process_id,
            UploadedFile.file_type == "fees",
        )
        .first()
        is not None
    )
    return _attach_has_fees_file(proc, has_fees)


@router.delete("/{process_id}")
def delete_process(process_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    proc = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    if proc.status == "running":
        raise HTTPException(status_code=400, detail="No se puede eliminar un proceso en ejecución")
    # Delete associated files from disk
    files = db.query(UploadedFile).filter(UploadedFile.process_id == process_id).all()
    for f in files:
        try:
            if os.path.exists(f.stored_path):
                os.remove(f.stored_path)
        except Exception:
            pass
    db.query(UploadedFile).filter(UploadedFile.process_id == process_id).delete()
    db.query(ProcessLog).filter(ProcessLog.process_id == process_id).delete()
    # Clean up TrueBook v2 tables (explicit delete for safety, not relying on CASCADE)
    from app.models.alert import RunAlert
    from app.models.bitso import BitsoBanregioMatch, BitsoReportLine, BitsoReport
    db.query(RunAdjustment).filter(RunAdjustment.process_id == process_id).delete()
    db.query(BanregioMovementClassification).filter(
        BanregioMovementClassification.process_id == process_id
    ).delete()
    db.query(RunAlert).filter(RunAlert.process_id == process_id).delete()
    # Bitso chain: matches → lines → reports (delete in dependency order)
    db.query(BitsoBanregioMatch).filter(
        BitsoBanregioMatch.process_id == process_id
    ).delete()
    bitso_reports = db.query(BitsoReport).filter(
        BitsoReport.process_id == process_id
    ).all()
    for br in bitso_reports:
        db.query(BitsoReportLine).filter(BitsoReportLine.report_id == br.id).delete()
    db.query(BitsoReport).filter(BitsoReport.process_id == process_id).delete()
    db.delete(proc)
    db.commit()
    return {"message": "Proceso eliminado"}


@router.get("/{process_id}/progress", response_model=ProcessProgress)
def get_progress(process_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    proc = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    logs = (
        db.query(ProcessLog)
        .filter(ProcessLog.process_id == process_id)
        .order_by(ProcessLog.created_at.asc())
        .all()
    )
    return ProcessProgress(
        process_id=proc.id,
        status=proc.status,
        current_stage=proc.current_stage,
        progress=proc.progress,
        logs=[ProcessLogOut.from_orm(l) for l in logs],
    )


@router.post("/{process_id}/run")
def run_process(
    process_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proc = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    if proc.status == "running":
        raise HTTPException(status_code=400, detail="Process already running")

    proc.status = "running"
    proc.progress = 0
    db.commit()

    background_tasks.add_task(_run_full_process, process_id)
    return {"message": "Process started", "process_id": process_id}


@router.post("/{process_id}/reclassify")
def reclassify_process(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-run only Stage 8 (auto-classify) against the existing
    `BanregioResult.movements`.

    Useful when:
      - Stage 8 silently failed in a previous run
      - Classifier rules were updated and we want to re-classify without
        re-running the whole expensive pipeline (Mongo extraction,
        Kushki SFTP download, FEES re-parse, conciliations, etc.)

    Status policy:
      - Allowed on any process status except 'running' (avoid race with
        the live pipeline)
      - Requires `BanregioResult` to exist with at least one movement
    """
    proc = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    if proc.status == "running":
        raise HTTPException(
            status_code=409,
            detail="Cannot reclassify while pipeline is running — wait for it to finish",
        )

    br = db.query(BanregioResult).filter_by(process_id=process_id).first()
    movements = (br.movements if br else None) or []
    if not movements:
        raise HTTPException(
            status_code=409,
            detail=(
                "No Banregio movements available to reclassify. Upload a "
                "Banregio file and run the full pipeline first."
            ),
        )

    _log(db, process_id, "classification",
         f"Reclasificando {len(movements)} movimientos (manual trigger)...")
    try:
        classifications = auto_classify_all(movements)
        # Idempotent: clear + re-insert
        db.query(BanregioMovementClassification).filter(
            BanregioMovementClassification.process_id == process_id
        ).delete()
        db.commit()
        for cls_data in classifications:
            db.add(BanregioMovementClassification(
                process_id=process_id, **cls_data,
            ))
        db.commit()

        coverage_stats = compute_coverage(classifications)
        proc.coverage_pct = coverage_stats["coverage_pct"]
        db.commit()
        _log(
            db, process_id, "classification",
            f"Reclasificación completada: {coverage_stats['classified']}/"
            f"{coverage_stats['total_movements']} ({coverage_stats['coverage_pct']}% "
            f"cobertura). {coverage_stats['unclassified']} sin clasificar.",
        )

        # Re-run the kushki_vs_banregio cuadre with the fresh classifications
        # — Stage 8b in the pipeline does this automatically; we mirror it
        # here so /reclassify keeps the cuadre in sync without a full re-run.
        kvb_summary = None
        kr = db.query(KushkiResult).filter_by(process_id=process_id).first()
        if kr:
            try:
                tolerance = conciliation_engine.get_tolerance(db)
                cls_map = {c["movement_index"]: c["classification"] for c in classifications}
                kvb_v2 = conciliation_engine.conciliate_kushki_vs_banregio(
                    {"daily_summary": kr.daily_summary or []},
                    {"movements": movements},
                    tolerance=tolerance,
                    classifications=cls_map,
                )
                db.query(ConciliationResult).filter(
                    ConciliationResult.process_id == process_id,
                    ConciliationResult.conciliation_type == "kushki_vs_banregio",
                ).delete()
                db.add(ConciliationResult(
                    process_id=process_id,
                    conciliation_type="kushki_vs_banregio",
                    matched=kvb_v2["matched"],
                    differences=kvb_v2["differences"],
                    unmatched_kushki=kvb_v2["unmatched_kushki"],
                    unmatched_banregio=kvb_v2["unmatched_banregio"],
                    total_conciliated=kvb_v2["total_conciliated"],
                    total_difference=kvb_v2["total_difference"],
                ))
                db.commit()
                kvb_summary = {
                    "matched": len(kvb_v2["matched"]),
                    "unmatched_kushki": len(kvb_v2["unmatched_kushki"]),
                    "unmatched_banregio": len(kvb_v2["unmatched_banregio"]),
                }
            except Exception as e:
                logger.exception(
                    "Reclassify: kushki_vs_banregio re-cuadre failed for process %d",
                    process_id,
                )
                # Don't fail the whole endpoint — classifications are still good
                _log(db, process_id, "conciliation",
                     f"Re-cuadre Kushki↔Banregio falló — {type(e).__name__}: {e}",
                     "error")

        return {
            "message": "Reclassification complete",
            "coverage_pct": coverage_stats["coverage_pct"],
            "classified": coverage_stats["classified"],
            "total_movements": coverage_stats["total_movements"],
            "unclassified": coverage_stats["unclassified"],
            "kushki_vs_banregio": kvb_summary,
        }
    except Exception as e:
        logger.exception("Reclassify failed for process %d", process_id)
        _log(db, process_id, "classification",
             f"Reclasificación falló — {type(e).__name__}: {e}", "error")
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"{type(e).__name__}: {e}",
        )


@router.post("/{process_id}/reconcile")
def reconcile_process(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Transition a process from COMPLETED to RECONCILED.

    Requirements:
    - Process status must be 'completed'
    - Banregio coverage must be 100%
    - No pending adjustments
    - All deltas must be $0 or covered by approved adjustments
    """
    proc = db.query(AccountingProcess).filter(
        AccountingProcess.id == process_id
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    if proc.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Process must be in 'completed' status to reconcile (current: {proc.status})",
        )

    blockers = []

    # Check coverage
    coverage = proc.coverage_pct
    if coverage is None or float(coverage) < 100.0:
        blockers.append(
            f"Banregio coverage is {coverage or 0}% (must be 100%)"
        )

    # Check pending adjustments
    pending = (
        db.query(RunAdjustment)
        .filter(
            RunAdjustment.process_id == process_id,
            RunAdjustment.status == "pending",
        )
        .count()
    )
    if pending > 0:
        blockers.append(f"{pending} pending adjustment(s) must be approved or rejected")

    # Check that all conciliation deltas are zero or covered by approved adjustments
    conciliation_rows = (
        db.query(ConciliationResult)
        .filter(ConciliationResult.process_id == process_id)
        .all()
    )
    for cr in conciliation_rows:
        delta = float(cr.total_difference) if cr.total_difference else 0
        if abs(delta) > 0.01:  # tolerance of 1 centavo
            # Check if approved adjustments cover this delta
            approved_adj = (
                db.query(RunAdjustment)
                .filter(
                    RunAdjustment.process_id == process_id,
                    RunAdjustment.status == "approved",
                    RunAdjustment.conciliation_type == cr.conciliation_type,
                )
                .all()
            )
            adj_total = sum(
                float(a.amount) * (1 if a.direction == "ADD" else -1)
                for a in approved_adj
            )
            remaining = abs(delta) - abs(adj_total)
            if remaining > 0.01:
                blockers.append(
                    f"Conciliation '{cr.conciliation_type}' has unexplained delta "
                    f"of ${abs(delta):,.2f} MXN (adjustments cover ${abs(adj_total):,.2f})"
                )

    if blockers:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Cannot reconcile — blockers exist",
                "blockers": blockers,
            },
        )

    proc.status = "reconciled"
    proc.reconciled_by = current_user.id
    proc.reconciled_at = datetime.now(timezone.utc)
    db.commit()

    _log(db, process_id, "system", f"Proceso marcado como RECONCILED por {current_user.email}")
    return {"message": "Process reconciled", "status": "reconciled"}


@router.post("/{process_id}/unreconcile")
def unreconcile_process(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Revert a RECONCILED process back to COMPLETED for corrections."""
    proc = db.query(AccountingProcess).filter(
        AccountingProcess.id == process_id
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Process not found")
    if proc.status != "reconciled":
        raise HTTPException(status_code=400, detail="Process is not reconciled")

    proc.status = "completed"
    proc.reconciled_by = None
    proc.reconciled_at = None
    db.commit()

    _log(db, process_id, "system", f"Proceso reabierto a COMPLETED por {current_user.email}")
    return {"message": "Process reverted to completed", "status": "completed"}


def _run_full_process(process_id: int):
    """Background task: extract FEES, parse uploaded files, run conciliations."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        proc = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
        if not proc:
            return

        year = proc.period_year
        month = proc.period_month
        acquirers = proc.acquirers or []

        # ── Stage 1: Extract transactions from MongoDB ──────────────────────
        _set_stage(db, proc, "extracting_transactions", 10)
        _log(db, process_id, "mongo", f"Extrayendo transacciones {year}-{month:02d} de MongoDB...")
        try:
            transactions = mongo_extractor.extract_transactions(year, month, acquirers)
            _log(db, process_id, "mongo", f"{len(transactions)} transacciones extraídas")
        except Exception as e:
            _log(db, process_id, "mongo", f"Error extrayendo transacciones: {e}", "error")
            transactions = []

        # ── Stage 2: Extract withdrawals ────────────────────────────────────
        _set_stage(db, proc, "extracting_withdrawals", 25)
        _log(db, process_id, "mongo", "Extrayendo withdrawals...")
        try:
            withdrawals = mongo_extractor.extract_withdrawals(year, month)
            _log(db, process_id, "mongo", f"{len(withdrawals)} withdrawals extraídos")
        except Exception as e:
            _log(db, process_id, "mongo", f"Error en withdrawals: {e}", "warning")
            withdrawals = []

        # ── Stage 3: Extract refunds ────────────────────────────────────────
        _set_stage(db, proc, "extracting_refunds", 35)
        _log(db, process_id, "mongo", "Extrayendo refunds/autorefunds...")
        try:
            refunds = mongo_extractor.extract_refunds(year, month)
            _log(db, process_id, "mongo", f"{len(refunds)} refunds extraídos")
        except Exception as e:
            _log(db, process_id, "mongo", f"Error en refunds: {e}", "warning")
            refunds = []

        # ── Stage 4: Process FEES ───────────────────────────────────────────
        _set_stage(db, proc, "processing_fees", 50)
        _log(db, process_id, "fees", "Procesando y consolidando FEES...")
        tx_result = fees_processor.process_transactions(transactions)
        w_result = fees_processor.process_withdrawals(withdrawals)
        r_result = fees_processor.process_refunds(refunds)
        fees_data = fees_processor.consolidate_fees(tx_result, w_result, r_result)
        _log(db, process_id, "fees", f"FEES consolidados. Total fees: {fees_data['total_fees']}")

        # Save fees result
        existing = db.query(FeesResult).filter(FeesResult.process_id == process_id).first()
        if existing:
            db.delete(existing)
            db.commit()
        db.add(FeesResult(
            process_id=process_id,
            merchant_summary=fees_data["merchant_summary"],
            daily_breakdown=fees_data["daily_breakdown"],
            withdrawals_summary=fees_data["withdrawals_summary"],
            refunds_summary=fees_data["refunds_summary"],
            other_fees_summary=fees_data["other_fees_summary"],
            total_fees=fees_data["total_fees"],
        ))
        db.commit()

        # ── Stage 5: Ingest + Parse Kushki files ────────────────────────────
        _set_stage(db, proc, "parsing_kushki", 65)
        kushki_data = None

        # Optional auto-ingestion from SFTP (download monthly files into this process)
        if settings.KUSHKI_SFTP_ENABLED:
            if kushki_sftp.is_configured():
                sftp_dir = os.path.join(settings.UPLOAD_DIR, str(process_id), "auto_sftp_kushki")
                os.makedirs(sftp_dir, exist_ok=True)
                _log(db, process_id, "kushki_sftp", "Conectando a SFTP Kushki para descarga mensual...")
                try:
                    # Remove previous auto-downloaded records for idempotent re-runs.
                    auto_segment = os.path.join(str(process_id), "auto_sftp_kushki").replace(os.sep, "%")
                    previous_auto = (
                        db.query(UploadedFile)
                        .filter(
                            UploadedFile.process_id == process_id,
                            UploadedFile.file_type == "kushki",
                            UploadedFile.stored_path.like(f"%{auto_segment}%"),
                        )
                        .all()
                    )
                    for rec in previous_auto:
                        try:
                            if os.path.exists(rec.stored_path):
                                os.remove(rec.stored_path)
                        except Exception:
                            pass
                        db.delete(rec)
                    db.commit()

                    downloaded = kushki_sftp.download_month_files(year, month, sftp_dir)
                    for item in downloaded:
                        db.add(UploadedFile(
                            process_id=process_id,
                            file_type="kushki",
                            original_name=item.remote_name,
                            stored_path=item.local_path,
                            file_size=item.size,
                            status="uploaded",
                        ))
                    db.commit()
                    _log(db, process_id, "kushki_sftp", f"SFTP Kushki: {len(downloaded)} archivo(s) descargado(s)")
                except Exception as e:
                    _log(db, process_id, "kushki_sftp", f"Error en descarga SFTP Kushki: {e}", "warning")
            else:
                _log(
                    db,
                    process_id,
                    "kushki_sftp",
                    "KUSHKI_SFTP_ENABLED=true pero faltan credenciales/configuración (se omite auto-descarga)",
                    "warning",
                )

        kushki_files = (
            db.query(UploadedFile)
            .filter(UploadedFile.process_id == process_id, UploadedFile.file_type == "kushki")
            .all()
        )

        if kushki_files:
            from app.services.kushki_parser import parse_kushki, merge_kushki_results
            parsed_results = []
            for f in kushki_files:
                _log(db, process_id, "kushki", f"Parseando {f.original_name}...")
                try:
                    with open(f.stored_path, "rb") as fp:
                        content = fp.read()
                    result = parse_kushki(content, f.original_name)
                    parsed_results.append(result)
                    f.status = "parsed"
                except Exception as e:
                    _log(db, process_id, "kushki", f"Error parseando {f.original_name}: {e}", "error")
                    f.status = "error"
            db.commit()

            if parsed_results:
                kushki_data = merge_kushki_results(parsed_results)
                existing = db.query(KushkiResult).filter(KushkiResult.process_id == process_id).first()
                if existing:
                    db.delete(existing)
                    db.commit()
                db.add(KushkiResult(
                    process_id=process_id,
                    daily_summary=kushki_data["daily_summary"],
                    merchant_detail=kushki_data["merchant_detail"],
                    total_net_deposit=kushki_data["total_net_deposit"],
                ))
                db.commit()
                _log(
                    db,
                    process_id,
                    "kushki",
                    f"Kushki consolidado desde {len(parsed_results)} archivo(s). Net deposit total: {kushki_data['total_net_deposit']}",
                )
            else:
                _log(db, process_id, "kushki", "No se pudo parsear ningún archivo Kushki", "warning")
        else:
            _log(db, process_id, "kushki", "No hay archivos Kushki (manuales o SFTP) para procesar", "warning")

        # ── Stage 5b: Ingest Bitso deposits from Bitso SPEI v2 API ─────────
        if settings.BITSO_API_ENABLED:
            from app.services import bitso_api
            from app.services.bitso_parser import parse_bitso_api_deposits
            from app.models.bitso import BitsoReport, BitsoReportLine, BitsoBanregioMatch

            if bitso_api.is_configured():
                _log(db, process_id, "bitso_api", "Conectando a Bitso API para descargar depósitos SPEI...")
                try:
                    deposits = bitso_api.download_monthly_deposits(year, month)
                    _log(db, process_id, "bitso_api", f"Bitso API: {len(deposits)} depósito(s) SPEI descargado(s)")

                    if deposits:
                        # Persist the raw payload to disk so it shows up in SFTP/API downloads
                        import json as _json
                        api_dir = os.path.join(settings.UPLOAD_DIR, str(process_id), "auto_bitso_api")
                        os.makedirs(api_dir, exist_ok=True)
                        fname = f"sftp_bitso_api_{year}_{month:02d}.json"
                        fpath = os.path.join(api_dir, fname)

                        # Idempotent: remove previous auto-Bitso file row + file
                        auto_segment = os.path.join(str(process_id), "auto_bitso_api").replace(os.sep, "%")
                        prev_files = (
                            db.query(UploadedFile)
                            .filter(
                                UploadedFile.process_id == process_id,
                                UploadedFile.file_type == "bitso",
                                UploadedFile.stored_path.like(f"%{auto_segment}%"),
                            )
                            .all()
                        )
                        for rec in prev_files:
                            try:
                                if os.path.exists(rec.stored_path):
                                    os.remove(rec.stored_path)
                            except Exception:
                                pass
                            db.delete(rec)
                        db.commit()

                        raw_bytes = _json.dumps(deposits, default=str).encode("utf-8")
                        with open(fpath, "wb") as fp:
                            fp.write(raw_bytes)

                        file_rec = UploadedFile(
                            process_id=process_id,
                            file_type="bitso",
                            original_name=fname,
                            stored_path=fpath,
                            file_size=len(raw_bytes),
                            status="uploaded",
                        )
                        db.add(file_rec)
                        db.commit()
                        db.refresh(file_rec)

                        # Revert existing 'bitso' classifications + remove previous auto report
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
                                cls.notes = "Revertido por re-sync Bitso API"
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

                        # Parse API payload → BitsoReport + lines
                        parsed = parse_bitso_api_deposits(deposits)
                        report = BitsoReport(
                            process_id=process_id,
                            file_id=file_rec.id,
                            period_start=parsed["period_start"],
                            period_end=parsed["period_end"],
                            total_rows=len(parsed["lines"]),
                            total_amount=parsed["total_amount"],
                        )
                        db.add(report)
                        db.commit()
                        db.refresh(report)

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
                        file_rec.status = "parsed"
                        db.commit()
                        _log(
                            db, process_id, "bitso_api",
                            f"Bitso persistido: {len(parsed['lines'])} líneas, total ${parsed['total_amount']:,.2f}",
                        )
                except Exception as e:
                    _log(db, process_id, "bitso_api", f"Error en descarga Bitso API: {e}", "warning")
            else:
                _log(
                    db, process_id, "bitso_api",
                    "BITSO_API_ENABLED=true pero faltan BITSO_API_KEY/SECRET (se omite auto-descarga)",
                    "warning",
                )

        # ── Stage 6: Parse Banregio ─────────────────────────────────────────
        _set_stage(db, proc, "parsing_banregio", 75)
        banregio_files = (
            db.query(UploadedFile)
            .filter(UploadedFile.process_id == process_id, UploadedFile.file_type == "banregio")
            .all()
        )
        banregio_data = None
        if banregio_files:
            from app.services.banregio_parser import parse_banregio
            all_movements = []
            all_deposits = []
            for f in banregio_files:
                _log(db, process_id, "banregio", f"Parseando {f.original_name}...")
                try:
                    with open(f.stored_path, "rb") as fp:
                        content = fp.read()
                    result = parse_banregio(content, f.original_name)
                    all_movements.extend(result["movements"])
                    all_deposits.extend(result["deposit_column"])
                    f.status = "parsed"
                except Exception as e:
                    _log(db, process_id, "banregio", f"Error: {e}", "error")
                    f.status = "error"
            db.commit()

            total_credits = sum(m.get("credit", 0) for m in all_movements)
            banregio_data = {
                "movements": all_movements,
                "summary": {"total_credits": round(total_credits, 6)},
                "deposit_column": all_deposits,
            }
            existing = db.query(BanregioResult).filter(BanregioResult.process_id == process_id).first()
            if existing:
                db.delete(existing)
                db.commit()
            db.add(BanregioResult(
                process_id=process_id,
                movements=all_movements,
                summary=banregio_data["summary"],
            ))
            db.commit()
            _log(db, process_id, "banregio", f"Banregio procesado. {len(all_movements)} movimientos")
        else:
            _log(db, process_id, "banregio", "No hay archivos Banregio cargados", "warning")

        # ── Stage 7: Conciliations ──────────────────────────────────────────
        _set_stage(db, proc, "conciliating", 88)
        _log(db, process_id, "conciliation", "Ejecutando conciliaciones...")

        # Delete previous conciliation results
        db.query(ConciliationResult).filter(ConciliationResult.process_id == process_id).delete()
        db.commit()

        # Read configurable tolerance from DB
        tolerance = conciliation_engine.get_tolerance(db)
        _log(db, process_id, "conciliation", f"Tolerancia configurada: {tolerance}")

        # FEES conciliation
        fees_concil = conciliation_engine.conciliate_fees(fees_data)
        db.add(ConciliationResult(
            process_id=process_id,
            conciliation_type="fees",
            matched=fees_concil["matched"],
            differences=fees_concil["differences"],
            total_conciliated=fees_concil["total_conciliated"],
            total_difference=fees_concil["total_difference"],
        ))

        if kushki_data:
            # Kushki daily
            kd_concil = conciliation_engine.conciliate_kushki_daily(kushki_data, tolerance=tolerance)
            db.add(ConciliationResult(
                process_id=process_id,
                conciliation_type="kushki_daily",
                matched=kd_concil["matched"],
                differences=kd_concil["differences"],
                total_conciliated=kd_concil["total_conciliated"],
                total_difference=kd_concil["total_difference"],
            ))

            if banregio_data:
                # Kushki vs Banregio
                kvb_concil = conciliation_engine.conciliate_kushki_vs_banregio(
                    kushki_data, banregio_data, tolerance=tolerance,
                )
                db.add(ConciliationResult(
                    process_id=process_id,
                    conciliation_type="kushki_vs_banregio",
                    matched=kvb_concil["matched"],
                    differences=kvb_concil["differences"],
                    unmatched_kushki=kvb_concil["unmatched_kushki"],
                    unmatched_banregio=kvb_concil["unmatched_banregio"],
                    total_conciliated=kvb_concil["total_conciliated"],
                    total_difference=kvb_concil["total_difference"],
                ))
        db.commit()

        # ── Stage 8: Auto-classify Banregio movements ──────────────────────
        _set_stage(db, proc, "classifying", 92)
        coverage_stats = None

        # Defensive gate: read movements from BanregioResult (single source
        # of truth in the DB), not the in-memory `banregio_data` variable
        # — if Stage 6 partially succeeded but `banregio_data` got mutated
        # to an empty list, we still want Stage 8 to run against whatever
        # was committed to BanregioResult.
        br_for_classify = db.query(BanregioResult).filter_by(process_id=process_id).first()
        movements_to_classify = (br_for_classify.movements if br_for_classify else None) or []

        if movements_to_classify:
            _log(db, process_id, "classification", "Auto-clasificando movimientos Banregio...")
            try:
                classifications = auto_classify_all(movements_to_classify)

                # Clear previous classifications for idempotent re-runs
                db.query(BanregioMovementClassification).filter(
                    BanregioMovementClassification.process_id == process_id
                ).delete()
                db.commit()

                for cls_data in classifications:
                    db.add(BanregioMovementClassification(
                        process_id=process_id,
                        **cls_data,
                    ))
                db.commit()

                coverage_stats = compute_coverage(classifications)
                proc.coverage_pct = coverage_stats["coverage_pct"]
                db.commit()
                _log(
                    db, process_id, "classification",
                    f"Clasificación completada: {coverage_stats['classified']}/{coverage_stats['total_movements']} "
                    f"({coverage_stats['coverage_pct']}% cobertura). "
                    f"{coverage_stats['unclassified']} sin clasificar.",
                )
            except Exception as e:
                # Promoted from "warning" to "error" so the failure is
                # observable in (a) Railway logs via logger.exception
                # and (b) ProcessLog with level=error so FinOps sees it
                # in the UI. Also persist coverage_pct=0 explicitly so
                # the v2 report endpoint's classification-count guard
                # fires instead of silently emitting an empty report.
                logger.exception(
                    "Stage 8 auto_classify_all failed for process %d", process_id,
                )
                _log(
                    db, process_id, "classification",
                    f"FATAL: auto-clasificación falló — {type(e).__name__}: {e}",
                    "error",
                )
                # Roll back any half-inserted classifications from this
                # failed pass, then mark coverage as zero.
                try:
                    db.rollback()
                except Exception:
                    pass
                try:
                    db.query(BanregioMovementClassification).filter(
                        BanregioMovementClassification.process_id == process_id
                    ).delete()
                    proc.coverage_pct = 0
                    db.commit()
                except Exception:
                    pass
        else:
            _log(
                db, process_id, "classification",
                "Saltando Stage 8 — no hay movimientos Banregio para clasificar",
                "warning",
            )

        # ── Stage 8b: Re-run kushki_vs_banregio with classifications ─────
        # The Stage 7 invocation runs without classifications (they don't
        # exist yet) and historically used the parser's `deposit_column`
        # which was always-empty for the Banregio Excel format → 0 matches
        # silently. Now that classifications are populated we re-run the
        # cuadre with `kushki_acquirer`-only filtering, which is what the
        # spec actually intends. Overwrites the Stage 7 placeholder row.
        if banregio_data and movements_to_classify:
            try:
                cls_rows = (
                    db.query(BanregioMovementClassification)
                    .filter_by(process_id=process_id)
                    .all()
                )
                cls_map = {c.movement_index: c.classification for c in cls_rows}
                kvb_v2 = conciliation_engine.conciliate_kushki_vs_banregio(
                    kushki_data,
                    {"movements": movements_to_classify, "deposit_column": banregio_data.get("deposit_column", [])},
                    tolerance=tolerance,
                    classifications=cls_map,
                )
                # Replace the Stage 7 placeholder
                db.query(ConciliationResult).filter(
                    ConciliationResult.process_id == process_id,
                    ConciliationResult.conciliation_type == "kushki_vs_banregio",
                ).delete()
                db.add(ConciliationResult(
                    process_id=process_id,
                    conciliation_type="kushki_vs_banregio",
                    matched=kvb_v2["matched"],
                    differences=kvb_v2["differences"],
                    unmatched_kushki=kvb_v2["unmatched_kushki"],
                    unmatched_banregio=kvb_v2["unmatched_banregio"],
                    total_conciliated=kvb_v2["total_conciliated"],
                    total_difference=kvb_v2["total_difference"],
                ))
                db.commit()
                _log(
                    db, process_id, "conciliation",
                    f"Cuadre Kushki↔Banregio: {len(kvb_v2['matched'])} matched, "
                    f"{len(kvb_v2['unmatched_kushki'])} unmatched_kushki, "
                    f"{len(kvb_v2['unmatched_banregio'])} unmatched_banregio",
                )
            except Exception as e:
                logger.exception("Stage 8b kushki_vs_banregio failed for process %d", process_id)
                _log(
                    db, process_id, "conciliation",
                    f"Stage 8b cuadre falló — {type(e).__name__}: {e}",
                    "error",
                )
                try:
                    db.rollback()
                except Exception:
                    pass

        # ── Stage 9: Generate alerts ───────────────────────────────────────
        _set_stage(db, proc, "alerting", 96)
        try:
            concil_data = []
            conciliation_rows = db.query(ConciliationResult).filter(
                ConciliationResult.process_id == process_id
            ).all()
            for cr in conciliation_rows:
                concil_data.append({
                    "conciliation_type": cr.conciliation_type,
                    "total_difference": float(cr.total_difference) if cr.total_difference else 0,
                })

            pending_adj = db.query(RunAdjustment).filter(
                RunAdjustment.process_id == process_id,
                RunAdjustment.status == "pending",
            ).count()

            alerts = alert_engine.evaluate_alerts(
                db=db,
                process_id=process_id,
                coverage_stats=coverage_stats,
                conciliation_results=concil_data,
                pending_adjustments=pending_adj,
                has_kushki_data=kushki_data is not None,
                has_banregio_data=banregio_data is not None,
            )
            _log(db, process_id, "alerts", f"{len(alerts)} alerta(s) generada(s)")
        except Exception as e:
            _log(db, process_id, "alerts", f"Error generando alertas: {e}", "warning")

        # ── Done ────────────────────────────────────────────────────────────
        proc.status = "completed"
        proc.current_stage = "done"
        proc.progress = 100
        db.commit()
        _log(db, process_id, "system", "Proceso completado exitosamente")

    except Exception as e:
        logger.exception(f"Process {process_id} failed: {e}")
        db.rollback()
        proc = db.query(AccountingProcess).filter(AccountingProcess.id == process_id).first()
        if proc:
            proc.status = "failed"
            proc.error_message = str(e)
            db.commit()
        try:
            _log(db, process_id, "system", f"Error fatal: {e}", "error")
        except Exception:
            pass
    finally:
        db.close()
