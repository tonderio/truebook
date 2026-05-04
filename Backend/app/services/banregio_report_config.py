"""
Typed config accessor for the Banregio Reconciliation Report v2.

Reads/seeds keys in the existing `reconciliation_config` key-value table
(see `app/models/alert.py:ReconciliationConfig`). Avoids a new model + a
migration — the table already exists for `conciliation_tolerance` etc.

Single source of truth for v2 thresholds, Bitso merchant grouping, and
the (FinOps-flagged) pending-transfer merchants. All values are
period-agnostic by default; pass `period_key` to namespace per period
(e.g. "2026-03") if you ever need monthly overrides.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.alert import ReconciliationConfig


# ── default seed values (FinOps-confirmed in spec v2) ────────────────────

DEFAULTS: dict[str, tuple[Any, str]] = {
    # Bitso merchant groups (spec §5.3)
    "bitso_grupo1": (
        ["BCGAME", "Fun MX", "Stadiobet"],
        "Bitso merchants where Tonder liquida usuarios directamente — "
        "los SPEIs salen de Bitso a usuarios finales, NO impactan Banregio.",
    ),
    "bitso_grupo2": (
        ["CampoBet", "Artilu MX"],
        "Bitso merchants donde Tonder repone saldo — los SPEIs SÍ impactan "
        "Banregio (CampoBet activo; Artilu MX puede estar pendiente).",
    ),

    # Thresholds (spec §4.2.8 + §4.3.3)
    "umbral_diferencia_menor": (
        500.00,
        "MXN — diferencia por debajo de este umbral se clasifica como menor.",
    ),
    "umbral_alerta_grande": (
        500.00,
        "MXN — diferencia por encima de este umbral dispara alerta CRITICAL.",
    ),

    # Operational FinOps state — pending transfers known but not yet received
    # (sourced from spec checklist; updated by FinOps as they resolve them)
    "pending_transfer_merchants": (
        [
            {"merchant": "Artilu MX", "amount": 37803.00, "source": "bitso",
             "note": "Pending transfer from Bitso (Rolling Reserve mgmt project)"},
            {"merchant": "STP/Kashio", "amount": 25027.00, "source": "stp",
             "note": "Pending transfer"},
            {"merchant": "CampoBet", "amount": 333117.00, "source": "bitso",
             "note": "Pending transfer"},
            {"merchant": "OXXOPay", "amount": 4292.00, "source": "oxxopay",
             "note": "Minor discrepancy — confirm if Pagsmile USDT payment fee"},
        ],
        "FinOps-flagged transfers expected but not yet landed in Banregio. "
        "Drives PENDING_TRANSFER alerts. Updated manually by FinOps.",
    ),

    # Display / locale (spec §6, §7)
    "currency": ("MXN", "Reporting currency."),
    "iva_rate": (0.16, "IVA tax rate applied to fees."),
    "timezone": ("UTC-6", "Operating timezone for cash-basis criterion."),
}


# ── access helpers ───────────────────────────────────────────────────────


def _get_raw(db: Session, key: str) -> str | None:
    row = (
        db.query(ReconciliationConfig)
        .filter(ReconciliationConfig.config_key == key)
        .first()
    )
    return row.config_value if row else None


def get(db: Session, key: str, default: Any = None) -> Any:
    """Read a config value, JSON-parsing if it looks structured.

    Falls back to DEFAULTS[key], then to the explicit `default` arg.
    """
    raw = _get_raw(db, key)
    if raw is None:
        if key in DEFAULTS:
            return DEFAULTS[key][0]
        return default

    # Try JSON-parse first (lists, dicts, numbers, booleans). Fall back to raw string.
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def set_value(db: Session, key: str, value: Any, description: str | None = None,
              user_id: int | None = None) -> ReconciliationConfig:
    """Upsert a config row. Serializes structured values to JSON."""
    serialized = value if isinstance(value, str) else json.dumps(value)
    row = (
        db.query(ReconciliationConfig)
        .filter(ReconciliationConfig.config_key == key)
        .first()
    )
    if row is None:
        row = ReconciliationConfig(
            config_key=key,
            config_value=serialized,
            description=description,
            updated_by=user_id,
        )
        db.add(row)
    else:
        row.config_value = serialized
        if description is not None:
            row.description = description
        if user_id is not None:
            row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


def seed_defaults(db: Session, overwrite: bool = False) -> dict[str, str]:
    """Seed every DEFAULT key into the DB if missing.

    Args:
        overwrite: if True, replace existing values with the defaults.

    Returns:
        {key: status} where status is one of "created" | "exists" | "overwritten".
    """
    result: dict[str, str] = {}
    for key, (value, description) in DEFAULTS.items():
        existing = _get_raw(db, key)
        if existing is None:
            set_value(db, key, value, description)
            result[key] = "created"
        elif overwrite:
            set_value(db, key, value, description)
            result[key] = "overwritten"
        else:
            result[key] = "exists"
    return result


# ── typed accessors (call sites should use these, not get() directly) ────


def bitso_grupo1(db: Session) -> list[str]:
    """Bitso merchants that liquidate users directly (no Banregio impact)."""
    return list(get(db, "bitso_grupo1"))


def bitso_grupo2(db: Session) -> list[str]:
    """Bitso merchants where Tonder repones saldo (Banregio impact)."""
    return list(get(db, "bitso_grupo2"))


def umbral_diferencia_menor(db: Session) -> float:
    return float(get(db, "umbral_diferencia_menor"))


def umbral_alerta_grande(db: Session) -> float:
    return float(get(db, "umbral_alerta_grande"))


def pending_transfer_merchants(db: Session) -> list[dict]:
    """List of {merchant, amount, source, note} entries flagged by FinOps."""
    return list(get(db, "pending_transfer_merchants"))


def is_pending_transfer(db: Session, merchant_name: str, source: str | None = None) -> bool:
    """Quick check: is this merchant on the pending-transfer list?"""
    name_norm = (merchant_name or "").strip().lower()
    for entry in pending_transfer_merchants(db):
        if entry.get("merchant", "").strip().lower() == name_norm:
            if source is None or entry.get("source") == source:
                return True
    return False
