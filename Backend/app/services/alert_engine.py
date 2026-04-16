"""
Alert engine — evaluates reconciliation health and generates alerts.

Called at the end of each pipeline run and when coverage/adjustments change.
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from app.models.alert import RunAlert, ReconciliationConfig

logger = logging.getLogger(__name__)


def _get_config(db: Session, key: str, default: str = "0") -> str:
    """Get a reconciliation config value, or default if not found."""
    config = db.query(ReconciliationConfig).filter(
        ReconciliationConfig.config_key == key
    ).first()
    return config.config_value if config else default


def evaluate_alerts(
    db: Session,
    process_id: int,
    coverage_stats: Optional[Dict] = None,
    conciliation_results: Optional[List[Dict]] = None,
    pending_adjustments: int = 0,
    has_kushki_data: bool = True,
    has_banregio_data: bool = True,
):
    """
    Evaluate reconciliation health and create alerts.

    This is called at the end of _run_full_process and can be re-called
    after manual classifications or adjustment approvals.
    """
    # Clear previous alerts for this process (they're regenerated each time)
    db.query(RunAlert).filter(RunAlert.process_id == process_id).delete()
    db.commit()

    alerts = []

    # ── Data availability checks ───────────────────────────────────────
    if not has_kushki_data:
        alerts.append(RunAlert(
            process_id=process_id,
            alert_level="CRITICAL",
            alert_type="NO_KUSHKI_DATA",
            title="Sin datos Kushki",
            message="No hay archivos Kushki cargados ni descargados por SFTP para este período.",
        ))

    if not has_banregio_data:
        alerts.append(RunAlert(
            process_id=process_id,
            alert_level="CRITICAL",
            alert_type="NO_BANREGIO_DATA",
            title="Sin estado de cuenta Banregio",
            message="No hay archivos Banregio cargados para este período.",
        ))

    # ── Coverage checks ────────────────────────────────────────────────
    if coverage_stats:
        coverage_pct = coverage_stats.get("coverage_pct", 0)
        unclassified = coverage_stats.get("unclassified", 0)
        critical_coverage = float(_get_config(db, "banregio_critical_coverage_pct", "95"))

        if unclassified > 0:
            alerts.append(RunAlert(
                process_id=process_id,
                alert_level="UNCLASSIFIED",
                alert_type="UNCLASSIFIED_MOVEMENTS",
                title=f"{unclassified} movimientos sin clasificar",
                message=(
                    f"Hay {unclassified} movimientos Banregio sin clasificar. "
                    f"Cobertura actual: {coverage_pct}%. "
                    f"Esto bloquea el estado RECONCILED."
                ),
                metadata_json={
                    "unclassified_count": unclassified,
                    "coverage_pct": coverage_pct,
                },
            ))

        if coverage_pct < critical_coverage:
            alerts.append(RunAlert(
                process_id=process_id,
                alert_level="CRITICAL",
                alert_type="LOW_COVERAGE",
                title=f"Cobertura Banregio baja: {coverage_pct}%",
                message=(
                    f"La cobertura Banregio ({coverage_pct}%) está por debajo "
                    f"del umbral crítico ({critical_coverage}%)."
                ),
                metadata_json={"coverage_pct": coverage_pct, "threshold": critical_coverage},
            ))

    # ── Delta checks ───────────────────────────────────────────────────
    if conciliation_results:
        warn_threshold = float(_get_config(db, "banregio_warn_threshold_amount", "500.00"))

        for result in conciliation_results:
            ctype = result.get("conciliation_type", "")
            total_diff = abs(float(result.get("total_difference", 0) or 0))

            if total_diff == 0:
                continue

            if total_diff > warn_threshold:
                alerts.append(RunAlert(
                    process_id=process_id,
                    alert_level="CRITICAL",
                    alert_type="LARGE_DELTA",
                    title=f"Diferencia grande en {ctype}: ${total_diff:,.2f}",
                    message=(
                        f"La conciliación {ctype} tiene una diferencia de "
                        f"${total_diff:,.2f} MXN que supera el umbral de "
                        f"${warn_threshold:,.2f} MXN."
                    ),
                    metadata_json={
                        "conciliation_type": ctype,
                        "total_difference": total_diff,
                        "threshold": warn_threshold,
                    },
                ))
            else:
                alerts.append(RunAlert(
                    process_id=process_id,
                    alert_level="WARNING",
                    alert_type="DELTA_EXISTS",
                    title=f"Diferencia en {ctype}: ${total_diff:,.2f}",
                    message=(
                        f"La conciliación {ctype} tiene una diferencia de "
                        f"${total_diff:,.2f} MXN. Revisar antes del cierre."
                    ),
                    metadata_json={
                        "conciliation_type": ctype,
                        "total_difference": total_diff,
                    },
                ))

    # ── Pending adjustments check ──────────────────────────────────────
    if pending_adjustments > 0:
        alerts.append(RunAlert(
            process_id=process_id,
            alert_level="INFO",
            alert_type="PENDING_ADJUSTMENTS",
            title=f"{pending_adjustments} ajuste(s) pendiente(s)",
            message=(
                f"Hay {pending_adjustments} ajuste(s) sin aprobar. "
                f"Los ajustes pendientes bloquean el estado RECONCILED."
            ),
            metadata_json={"pending_count": pending_adjustments},
        ))

    # ── Save all alerts ────────────────────────────────────────────────
    for alert in alerts:
        db.add(alert)
    db.commit()

    # If no issues at all, add an OK alert
    if not alerts and has_kushki_data and has_banregio_data:
        ok_alert = RunAlert(
            process_id=process_id,
            alert_level="OK",
            alert_type="ALL_CLEAR",
            title="Conciliación sin problemas",
            message="Todos los movimientos clasificados, sin diferencias pendientes.",
        )
        db.add(ok_alert)
        db.commit()

    return [{"level": a.alert_level, "type": a.alert_type, "title": a.title} for a in alerts]
