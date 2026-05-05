"""
Alert generation for Sheet 3 — `Alertas` (spec §4.3.3).

Pure function: takes Sheet 2's per-acquirer stats + DB session + config
and returns an ordered list of alerts ready for rendering.

Decoupled from openpyxl so this is unit-testable and can later feed the
existing `RunAlert` table if FinOps decides to merge the two alert
streams.

Each alert is a dict:
    {
      "level": "INFO" | "WARNING" | "INVESTIGATION" | "CRITICAL",
      "type":  "TIMING_CAJA" | "PENDING_TRANSFER" | "DELTA_BITSO" |
               "MINOR_DELTA" | "LARGE_DELTA" | "COVERAGE_LOW" |
               "FEES_FILE_MISSING",
      "title": short string (col C),
      "message": longer explanation (col D),
    }

Ordering is deterministic: severity DESC then type ASC then title ASC.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services import banregio_report_config as cfg
from app.services import kushki_intransit
from app.models.process import AccountingProcess
from app.models.file import UploadedFile


# Severity ranking for sort order — higher = more urgent
LEVEL_RANK = {
    "CRITICAL": 4,
    "WARNING": 3,
    "INVESTIGATION": 2,
    "INFO": 1,
}


def _spanish_month(period_month: int) -> tuple[str, str]:
    """Return (full_lower, abbrev_lower) — e.g. ('marzo', 'mar')."""
    full = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ][period_month - 1]
    abbrev = full[:3]
    return full, abbrev


def _next_month_first_day_label(period_year: int, period_month: int) -> str:
    """'01-abr' for March, '01-ene' for December."""
    nm = period_month + 1 if period_month < 12 else 1
    months_short = ["ene", "feb", "mar", "abr", "may", "jun",
                    "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"01-{months_short[nm - 1]}"


def _last_day_label(period_year: int, period_month: int) -> str:
    """'31-mar' / '28-feb' etc."""
    import calendar
    last = calendar.monthrange(period_year, period_month)[1]
    months_short = ["ene", "feb", "mar", "abr", "may", "jun",
                    "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{last:02d}-{months_short[period_month - 1]}"


def generate(
    db: Session,
    process: AccountingProcess,
    sheet2_stats: dict[str, dict],
    coverage_pct: float,
    intransit_classification: dict | None = None,
    has_fees_file: bool | None = None,
) -> list[dict]:
    """Build the ordered alert list for Sheet 3.

    Args:
        db: SQLAlchemy session for config lookups.
        process: AccountingProcess (period_year, period_month, etc).
        sheet2_stats: dict returned by `sheet_por_adquirente.build()`,
            keys: kushki, bitso, oxxopay, stp, unlimit, resumen.
        coverage_pct: classification coverage (0–100).
        intransit_classification: full classify_rows() output. If None,
            we'll skip TIMING_CAJA detection.

    Returns: list of alert dicts in display order (most urgent first).
    """
    alerts: list[dict] = []

    threshold_minor = cfg.umbral_diferencia_menor(db)
    threshold_major = cfg.umbral_alerta_grande(db)
    pending_list = cfg.pending_transfer_merchants(db)
    pending_by_source = {
        (p.get("source"), (p.get("merchant") or "").strip().lower()): p
        for p in pending_list
    }

    full_month, abbrev = _spanish_month(process.period_month)
    period_label = f"{full_month} {process.period_year}"

    # ── 1) TIMING_CAJA ───────────────────────────────────────────────
    if intransit_classification:
        summary = kushki_intransit.summary_for_alert(intransit_classification)
        transit_total = summary.get("transit_total", 0)
        if transit_total and transit_total > 0:
            next_first = _next_month_first_day_label(process.period_year, process.period_month)
            last_day = _last_day_label(process.period_year, process.period_month)
            alerts.append({
                "level": "INFO",
                "type": "TIMING_CAJA",
                "title": "Depósito Kushki en tránsito",
                "message": (
                    f"${transit_total:,.2f} MXN de SR Kushki (txns {last_day}) "
                    f"depositados el {next_first}. Excluidos por criterio de caja."
                ),
            })

    # ── 2) PENDING_TRANSFER — Bitso (Artilu MX et al.) ──────────────
    bitso = sheet2_stats.get("bitso", {}) or {}
    artilu_recibido = bitso.get("artilu_recibido", 0)
    artilu_neto = bitso.get("artilu_neto_liquidar", 0)
    if artilu_neto > 0 and artilu_recibido == 0:
        alerts.append({
            "level": "WARNING",
            "type": "PENDING_TRANSFER",
            "title": "Artilu MX — Bitso pendiente",
            "message": (
                f"${artilu_neto:,.2f} MXN procesados por Bitso para Artilu MX "
                f"no han sido transferidos a Banregio."
            ),
        })

    # ── 3) PENDING_TRANSFER — STP (driven by FinOps config, not by diff
    #         sign, so it fires correctly even when FEES file is missing
    #         STP rows for the period) ──────────────────────────────────
    stp = sheet2_stats.get("stp", {}) or {}
    stp_neto = stp.get("neto_fees", 0)
    stp_banco = stp.get("total_banco", 0)
    stp_pending = next(
        (p for p in pending_list if p.get("source") == "stp"), None
    )
    if stp_pending:
        merchant_label = stp_pending.get("merchant", "Kashio")
        # The canonical pending amount from config (FinOps-flagged truth);
        # falls back to computed diff if the config lacks an amount.
        config_amount = float(stp_pending.get("amount") or 0)
        diff_amount = config_amount or abs(stp_neto - stp_banco)
        # Strip 'STP/' prefix to match gold-style title
        title_label = merchant_label.split("/")[-1] if "/" in merchant_label else merchant_label
        # Use computed values if FEES gave us real numbers, else fall back
        # to the config amount in the message.
        if stp_neto > 0:
            msg = (
                f"${diff_amount:,.2f} MXN diferencia STP: procesado "
                f"${stp_neto:,.2f} vs recibido ${stp_banco:,.2f}. Saldo "
                f"pendiente de transferencia STP."
            )
        else:
            msg = (
                f"${diff_amount:,.2f} MXN MXN pendiente de transferencia STP "
                f"(FinOps-flagged). Banco recibió ${stp_banco:,.2f}; "
                f"saldo confirmado por STP/Kashio."
            )
        alerts.append({
            "level": "WARNING",
            "type": "PENDING_TRANSFER",
            "title": f"STP — {title_label} pendiente",
            "message": msg,
        })

    # ── 4) DELTA_BITSO — CampoBet diferencia in investigation ───────
    campo_diff = bitso.get("campobet_diferencia", 0)
    if abs(campo_diff) > threshold_major:
        campo_neto = bitso.get("campobet_neto_liquidar", 0)
        campo_banco = bitso.get("campobet_recibido", 0)
        alerts.append({
            "level": "INVESTIGATION",
            "type": "DELTA_BITSO",
            "title": "CampoBet Bitso — diferencia en investigación",
            "message": (
                f"${abs(campo_diff):,.2f} MXN entre neto FEES CampoBet "
                f"(${campo_neto:,.2f}) y SPEIs recibidos (${campo_banco:,.2f}). "
                f"Sin reporte de liquidación Bitso para validar."
            ),
        })

    # ── 5) MINOR_DELTA — OXXOPay et al ──────────────────────────────
    # Fires either from computed diff (when FEES data is complete) OR
    # from the FinOps pending-transfer config (when FEES is incomplete
    # for the period and the operator already knows the amount).
    oxxo = sheet2_stats.get("oxxopay", {}) or {}
    oxxo_diff = oxxo.get("diferencia", 0)
    oxxo_neto = oxxo.get("neto_fees", 0)
    oxxo_banco = oxxo.get("total_banco", 0)

    fired_oxxo_minor = False
    if oxxo_diff != 0 and abs(oxxo_diff) <= threshold_minor:
        alerts.append({
            "level": "INFO",
            "type": "MINOR_DELTA",
            "title": "OXXOPay — diferencia menor",
            "message": (
                f"${abs(oxxo_diff):,.2f} MXN entre neto FEES OXXOPay "
                f"(${oxxo_neto:,.2f}) y SPEIs recibidos (${oxxo_banco:,.2f}). "
                f"Bajo umbral de revisión — confirmar si corresponde a "
                f"comisión Pagsmile o ajuste menor."
            ),
        })
        fired_oxxo_minor = True

    # Config-driven fallback: when FEES is incomplete for the period, the
    # computed diff is meaningless. FinOps's pending-transfer list IS the
    # operational truth — if they've classified an OXXOPay item as a
    # known minor discrepancy under review, render it as MINOR_DELTA
    # regardless of the arithmetic threshold.
    if not fired_oxxo_minor:
        oxxo_pending = next(
            (p for p in pending_list if p.get("source") == "oxxopay"), None
        )
        if oxxo_pending:
            amount = float(oxxo_pending.get("amount") or 0)
            if amount > 0:
                note = oxxo_pending.get("note") or "ajuste menor en revisión"
                alerts.append({
                    "level": "INFO",
                    "type": "MINOR_DELTA",
                    "title": "OXXOPay — diferencia menor",
                    "message": (
                        f"${amount:,.2f} MXN entre neto FEES OXXOPay y SPEIs "
                        f"Pagsmile recibidos (${oxxo_banco:,.2f}). {note}."
                    ),
                })

    # ── 6) LARGE_DELTA — any acquirer with diff > umbral_grande and not
    #         already covered by another alert for the same acquirer.
    #         When the FEES file is missing rows for an acquirer (e.g.
    #         March's FEES file lacked OXXOPay/STP), the diff calculation
    #         will look huge — but those gaps are data-supply issues, not
    #         operational deltas. Skip LARGE_DELTA when banco>0 and
    #         neto_fees=0 (the signature of a missing FEES section).
    suppress_types = ("PENDING_TRANSFER", "DELTA_BITSO", "MINOR_DELTA", "LARGE_DELTA")
    for acq_label, stats_key, sheet2_diff_key in [
        ("Kushki", "kushki", "diferencia"),
        ("OXXOPay", "oxxopay", "diferencia"),
        ("STP", "stp", "diferencia"),
    ]:
        block = sheet2_stats.get(stats_key, {}) or {}
        d = block.get(sheet2_diff_key, 0)
        if abs(d) <= threshold_major:
            continue
        # Skip if already raised by another type for this acquirer
        if any(a["type"] in suppress_types
               and acq_label.lower() in a["title"].lower()
               for a in alerts):
            continue
        # Skip if this acquirer's FEES rows are missing (data gap, not delta)
        neto_fees = block.get("neto_fees", 0)
        banco = block.get("total_banco", 0)
        if neto_fees == 0 and banco > 0:
            continue
        alerts.append({
            "level": "CRITICAL",
            "type": "LARGE_DELTA",
            "title": f"{acq_label} — diferencia grande",
            "message": (
                f"${abs(d):,.2f} MXN diferencia en {acq_label} "
                f"(neto vs banco). Excede umbral de "
                f"${threshold_major:,.2f}; investigar."
            ),
        })

    # ── 7) COVERAGE_LOW ──────────────────────────────────────────────
    if coverage_pct < 100.0:
        alerts.append({
            "level": "WARNING",
            "type": "COVERAGE_LOW",
            "title": "Cobertura incompleta",
            "message": (
                f"Cobertura de clasificación: {coverage_pct:.1f}%. "
                f"Movimientos sin clasificar requieren revisión manual "
                f"antes de cerrar el período."
            ),
        })

    # ── 8) FEES_FILE_MISSING ─────────────────────────────────────────
    # Fires when classifications are populated (so the run is
    # operationally complete) but no FEES file was uploaded. Without it
    # the v2 report's per-acquirer "Neto a Liquidar" reads $0 for
    # OXXOPay / STP / Bitso, leaving the Resumen Consolidado with a
    # large unexplained delta. This is operational guidance, not a
    # blocker — close can still promote to reconciled if the
    # arithmetic delta is covered by approved adjustments.
    if coverage_pct >= 100.0:
        # Caller can pre-supply has_fees_file (e.g. sheet_alertas.py
        # already needed to know this) to avoid the DB hit. None means
        # "look it up myself".
        if has_fees_file is None:
            has_fees_file = (
                db.query(UploadedFile.id)
                .filter(
                    UploadedFile.process_id == process.id,
                    UploadedFile.file_type == "fees",
                )
                .first()
                is not None
            )
        if not has_fees_file:
            full_month_upper = full_month.upper()
            alerts.append({
                "level": "INFO",
                "type": "FEES_FILE_MISSING",
                "title": "FEES file pendiente",
                "message": (
                    f"No se ha subido el archivo "
                    f"FEES_{full_month_upper}_{process.period_year}_FINAL.xlsx. "
                    f"El reporte v2 mostrará $0 en Neto a Liquidar para "
                    f"OXXOPay / STP / Bitso hasta que FinOps lo provea. "
                    f"Sube el archivo y haz clic en Re-clasificar para "
                    f"poblar los cuadres por adquirente."
                ),
            })

    # Preserve generation order — it already follows the spec's narrative
    # flow (timing context → operational pending items → investigation
    # gaps → minor/info items at the end). Stakeholders read top-to-
    # bottom expecting this storyline; re-sorting by severity would put
    # TIMING_CAJA last and break the pattern.
    return alerts
