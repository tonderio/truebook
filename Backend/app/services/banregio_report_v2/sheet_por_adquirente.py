"""
Sheet 2 orchestrator — `Por Adquirente` (spec §4.2).

Composes the five acquirer sections + Resumen Consolidado in order.
Each section gets the data it needs and returns a stats dict the resumen
uses to build the final consolidated table.

Data orchestration:
  1. Load Banregio movements + classifications (one DB hit each)
  2. Load KushkiResult + in-transit summary
  3. Load FEES file rows (filtered per-acquirer)
  4. Load v2 config (G1/G2, thresholds, pending list)
  5. Walk sections top-to-bottom; collect stats from each
  6. Render Resumen using all collected stats
"""
from __future__ import annotations

from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy.orm import Session

from app.models.process import AccountingProcess
from app.models.result import KushkiResult, BanregioResult
from app.models.classification import BanregioMovementClassification
from app.models.file import UploadedFile

from app.services import banregio_report_config as cfg
from app.services import kushki_intransit
from app.services import fees_file_parser

from . import styles as st
from .por_adquirente import (
    _common as cm,
    kushki as kushki_section,
    bitso as bitso_section,
    oxxopay as oxxopay_section,
    stp as stp_section,
    unlimit as unlimit_section,
    resumen as resumen_section,
)


SPANISH_MONTHS = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]

COLUMN_WIDTHS = {
    "A": 22.0, "B": 30.0, "C": 16.0, "D": 14.0,
    "G": 16.0, "H": 14.0, "K": 13.0, "M": 11.0, "N": 13.0,
    "O": 15.0, "P": 18.0, "Q": 11.0, "R": 18.0, "S": 35.0,
}


def _load_fees_file_for_process(db: Session, process_id: int) -> dict | None:
    """Find and parse the FEES file uploaded to this process, if any."""
    fees_file = (
        db.query(UploadedFile)
        .filter_by(process_id=process_id, file_type="fees")
        .order_by(UploadedFile.id.desc())
        .first()
    )
    if not fees_file:
        return None
    try:
        with open(fees_file.stored_path, "rb") as f:
            content = f.read()
        return fees_file_parser.parse_fees_file(content, fees_file.original_name)
    except Exception:
        return None


def build(ws: Worksheet, db: Session, process: AccountingProcess) -> dict:
    """Populate `ws` with the full Por Adquirente sheet."""
    # ── 1. Load all data sources ────────────────────────────────────
    br = db.query(BanregioResult).filter_by(process_id=process.id).first()
    movements = (br.movements if br else []) or []

    classifications = (
        db.query(BanregioMovementClassification)
        .filter_by(process_id=process.id)
        .all()
    )
    by_idx = {c.movement_index: c for c in classifications}

    kr = db.query(KushkiResult).filter_by(process_id=process.id).first()
    kushki_merchant_detail = (kr.merchant_detail if kr else []) or []

    intransit = kushki_intransit.classify_rows(
        (kr.daily_summary if kr else []) or [],
        process.period_year, process.period_month,
    )
    intransit_summary = kushki_intransit.summary_for_alert(intransit)

    fees = _load_fees_file_for_process(db, process.id) or {
        "detalle": [],
        "totals_by_merchant_acquirer": {},
        "totals_by_acquirer": {},
    }
    fees_detalle = fees.get("detalle", [])

    # ── 2. v2 config ────────────────────────────────────────────────
    g1 = cfg.bitso_grupo1(db)
    g2 = cfg.bitso_grupo2(db)
    pending = cfg.pending_transfer_merchants(db)
    umbral_minor = cfg.umbral_diferencia_menor(db)
    umbral_major = cfg.umbral_alerta_grande(db)

    # ── 3. Global header (rows 1-2) ─────────────────────────────────
    month_name = SPANISH_MONTHS[process.period_month - 1]
    period_label = f"{month_name} {process.period_year}"
    row = cm.write_global_header(ws, period_label)

    # Column widths
    for col, width in COLUMN_WIDTHS.items():
        ws.column_dimensions[col].width = width

    # ── 4. KUSHKI ───────────────────────────────────────────────────
    row, kushki_stats = kushki_section.write(
        ws, row,
        banregio_movements=movements,
        classifications_by_idx=by_idx,
        kushki_merchant_detail=kushki_merchant_detail,
        intransit_summary=intransit_summary,
        fees_by_merchant_acquirer=fees.get("totals_by_merchant_acquirer", {}),
        period_year=process.period_year,
        period_month=process.period_month,
    )

    # ── 5. BITSO ────────────────────────────────────────────────────
    fees_bitso = [r for r in fees_detalle if r.get("adquirente") == "bitso"]
    row, bitso_stats = bitso_section.write(
        ws, row,
        banregio_movements=movements,
        classifications_by_idx=by_idx,
        fees_detalle_bitso=fees_bitso,
        bitso_grupo1=g1,
        bitso_grupo2=g2,
        pending_transfer_merchants=pending,
        umbral_minor=umbral_minor,
        umbral_major=umbral_major,
    )

    # ── 6. OXXOPAY ──────────────────────────────────────────────────
    fees_oxxo = [r for r in fees_detalle if r.get("adquirente") == "oxxopay"]
    row, oxxopay_stats = oxxopay_section.write(
        ws, row,
        banregio_movements=movements,
        classifications_by_idx=by_idx,
        fees_detalle_oxxopay=fees_oxxo,
        period_label=period_label,
        umbral_minor=umbral_minor,
    )

    # ── 7. STP ──────────────────────────────────────────────────────
    fees_stp = [r for r in fees_detalle if r.get("adquirente") == "stp"]
    row, stp_stats = stp_section.write(
        ws, row,
        banregio_movements=movements,
        classifications_by_idx=by_idx,
        fees_detalle_stp=fees_stp,
        pending_transfer_merchants=pending,
        umbral_minor=umbral_minor,
    )

    # ── 8. UNLIMIT ──────────────────────────────────────────────────
    row, unlimit_stats = unlimit_section.write(
        ws, row,
        banregio_movements=movements,
        classifications_by_idx=by_idx,
    )

    # ── 9. RESUMEN CONSOLIDADO ──────────────────────────────────────
    row, resumen_stats = resumen_section.write(
        ws, row,
        kushki_stats=kushki_stats,
        bitso_stats=bitso_stats,
        oxxopay_stats=oxxopay_stats,
        stp_stats=stp_stats,
        unlimit_stats=unlimit_stats,
        umbral_minor=umbral_minor,
        umbral_major=umbral_major,
    )

    return {
        "kushki": kushki_stats,
        "bitso": bitso_stats,
        "oxxopay": oxxopay_stats,
        "stp": stp_stats,
        "unlimit": unlimit_stats,
        "resumen": resumen_stats,
    }
