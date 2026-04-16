"""
Reconciliation alerts CRUD + configuration.

Alerts are generated during pipeline execution and at post-conciliation.
They track reconciliation health and block RECONCILED status when unresolved.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.alert import RunAlert, ReconciliationConfig
from app.schemas.alert import AlertOut, ConfigOut, ConfigUpdate

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ── Reconciliation Config (static paths FIRST to avoid route shadowing) ──

@router.get("/config/all", response_model=List[ConfigOut])
def list_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all reconciliation config values."""
    return db.query(ReconciliationConfig).order_by(
        ReconciliationConfig.config_key
    ).all()


@router.put("/config/{config_key}", response_model=ConfigOut)
def update_config(
    config_key: str,
    body: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a reconciliation config value."""
    config = db.query(ReconciliationConfig).filter(
        ReconciliationConfig.config_key == config_key
    ).first()
    if not config:
        raise HTTPException(status_code=404, detail=f"Config key '{config_key}' not found")

    config.config_value = body.config_value
    config.updated_by = current_user.id
    db.commit()
    db.refresh(config)
    return config


# ── Alert CRUD (parameterized paths AFTER static paths) ──────────────────

@router.get("/{process_id}", response_model=List[AlertOut])
def list_alerts(
    process_id: int,
    level: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all alerts for a process, optionally filtered by level."""
    query = db.query(RunAlert).filter(RunAlert.process_id == process_id)
    if level:
        query = query.filter(RunAlert.alert_level == level)
    return query.order_by(RunAlert.created_at.desc()).all()


@router.get("/{process_id}/summary")
def alert_summary(
    process_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get alert summary: counts by level, has unacknowledged."""
    alerts = (
        db.query(RunAlert)
        .filter(RunAlert.process_id == process_id)
        .all()
    )

    by_level = {}
    unacknowledged = 0
    for a in alerts:
        by_level[a.alert_level] = by_level.get(a.alert_level, 0) + 1
        if not a.is_acknowledged:
            unacknowledged += 1

    return {
        "total": len(alerts),
        "by_level": by_level,
        "unacknowledged": unacknowledged,
        "has_critical": by_level.get("CRITICAL", 0) > 0,
        "has_unclassified": by_level.get("UNCLASSIFIED", 0) > 0,
    }


@router.put("/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark an alert as acknowledged."""
    alert = db.query(RunAlert).filter(RunAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.is_acknowledged = True
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert
