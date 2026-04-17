"""
Connection Management endpoints — SFTP + API status, tests, logs, downloads.
"""
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.process import ProcessLog
from app.models.file import UploadedFile

from app.services.kushki_sftp import _build_config as kushki_config
from app.services.stp_sftp import _build_config as stp_config
from app.services.pagsmile_sftp import _build_config as pagsmile_config
from app.services.paysafe_sftp import _build_config as paysafe_config
from app.services.sftp_base import SFTPConnector
from app.services import bitso_api
from app.config import settings

router = APIRouter(prefix="/api/sftp", tags=["sftp"])

ACQUIRER_CONFIGS = {
    "kushki": kushki_config,
    "stp": stp_config,
    "pagsmile": pagsmile_config,
    "paysafe": paysafe_config,
}

ACQUIRER_LABELS = {
    "kushki": "Kushki",
    "stp": "STP",
    "pagsmile": "Pagsmile / OXXO Pay",
    "paysafe": "Paysafe",
    "bitso": "Bitso (API)",
}


def _acquirer_status(name: str, builder):
    """Build status dict for one SFTP acquirer. Never expose private keys."""
    cfg = builder()
    connector = SFTPConnector(cfg)
    return {
        "name": name,
        "label": ACQUIRER_LABELS.get(name, name),
        "kind": "sftp",
        "enabled": cfg.enabled,
        "is_configured": connector.is_configured(),
        "host": cfg.host or None,
        "username": cfg.username or None,
        "port": cfg.port,
        "remote_dir": cfg.remote_dir,
    }


def _bitso_status():
    """Bitso uses an API, not SFTP. Shape matches other acquirers for UI parity."""
    cfg = bitso_api._build_config()
    key_mask = None
    if cfg.api_key:
        # Show first 6 + last 4 chars, mask middle
        if len(cfg.api_key) > 12:
            key_mask = f"{cfg.api_key[:6]}***{cfg.api_key[-4:]}"
        else:
            key_mask = f"{cfg.api_key[:3]}***"
    return {
        "name": "bitso",
        "label": ACQUIRER_LABELS["bitso"],
        "kind": "api",
        "enabled": cfg.enabled,
        "is_configured": bitso_api.is_configured(),
        "host": cfg.base_url,          # reuse "host" slot for base URL
        "username": key_mask,          # reuse "username" slot for masked API key
        "port": None,
        "remote_dir": "/spei/v2/deposits",
    }


@router.get("/status")
def sftp_status(current_user: User = Depends(get_current_user)):
    """List all acquirer connections (SFTP + API) with their config status."""
    acquirers = []
    for name, builder in ACQUIRER_CONFIGS.items():
        acquirers.append(_acquirer_status(name, builder))
    acquirers.append(_bitso_status())
    return {"acquirers": acquirers}


@router.post("/bitso/test")
def test_bitso_connection(current_user: User = Depends(get_current_user)):
    """Test Bitso API connection with a minimal request."""
    result = bitso_api.test_connection()
    return {
        "success": result.get("ok", False),
        "message": result.get("message"),
        "error": result.get("error"),
        "sample_created_at": result.get("sample_created_at"),
        "tested_at": datetime.utcnow().isoformat(),
    }


@router.get("/bitso/debug")
def debug_bitso_raw(
    year: int,
    month: int,
    max_pages: int = 20,
    current_user: User = Depends(get_current_user),
):
    """
    Diagnostic: fully paginates Bitso deposits using page_token and reports
    date distribution so we can see what months are accessible.
    """
    if not bitso_api.is_configured():
        return {"error": "Bitso API not configured"}
    try:
        start_date, end_date = bitso_api._month_bounds(year, month)
        all_items = []
        pages_fetched = 0
        token = None
        last_token = None

        for _ in range(max_pages):
            params = {"limit": 100}
            if token:
                params["page_token"] = token
            data = bitso_api._request("GET", "/spei/v2/deposits", params=params)
            items, next_token = bitso_api._extract_items_and_marker(data)
            if not items:
                break
            all_items.extend(items)
            pages_fetched += 1
            last_token = next_token
            if not next_token or next_token == token:
                break
            token = next_token

        # Count deposits per month
        from collections import Counter
        month_counter = Counter()
        for d in all_items:
            op_date = d.get("operation_date") or (d.get("created_at") or "")[:10]
            if op_date and len(op_date) >= 7:
                month_counter[op_date[:7]] += 1

        in_target = sum(
            1 for d in all_items
            if (d.get("operation_date") or "").startswith(f"{year:04d}-{month:02d}")
        )

        return {
            "target_month": f"{year:04d}-{month:02d}",
            "pages_fetched": pages_fetched,
            "total_deposits_loaded": len(all_items),
            "in_target_month": in_target,
            "deposits_by_month": dict(sorted(month_counter.items())),
            "pagination_ended_early": last_token in (None, "", token),
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/{acquirer}/test")
def test_sftp_connection(
    acquirer: str,
    current_user: User = Depends(get_current_user),
):
    """Test SFTP connection for an acquirer. Returns success + file count or error."""
    if acquirer not in ACQUIRER_CONFIGS:
        return {"success": False, "error": f"Unknown acquirer: {acquirer}", "tested_at": datetime.utcnow().isoformat()}

    cfg = ACQUIRER_CONFIGS[acquirer]()
    connector = SFTPConnector(cfg)

    if not connector.is_configured():
        return {
            "success": False,
            "error": "No configurado — faltan credenciales (host, username o llave SSH)",
            "tested_at": datetime.utcnow().isoformat(),
        }

    try:
        sftp = connector._connect()
        try:
            remote_dir = connector._choose_remote_dir(sftp)
            files = sftp.listdir(remote_dir)
            file_count = len(files)
        finally:
            connector._close(sftp)

        return {
            "success": True,
            "message": f"Conexión exitosa. {file_count} archivo(s) en {remote_dir}",
            "file_count": file_count,
            "remote_dir": remote_dir,
            "tested_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "tested_at": datetime.utcnow().isoformat(),
        }


@router.get("/logs")
def sftp_logs(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recent SFTP-related logs from process runs."""
    # Match SFTP stages AND API stages (bitso_api, etc.)
    from sqlalchemy import or_
    logs = (
        db.query(ProcessLog)
        .filter(or_(
            ProcessLog.stage.ilike("%sftp%"),
            ProcessLog.stage.ilike("%_api"),
        ))
        .order_by(ProcessLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id,
            "process_id": log.process_id,
            "stage": log.stage,
            "level": log.level,
            "message": log.message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/downloads")
def sftp_downloads(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recent files downloaded via SFTP."""
    files = (
        db.query(UploadedFile)
        .filter(UploadedFile.original_name.ilike("sftp_%"))
        .order_by(UploadedFile.uploaded_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": f.id,
            "process_id": f.process_id,
            "file_type": f.file_type,
            "original_name": f.original_name,
            "file_size": f.file_size,
            "status": f.status,
            "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
        }
        for f in files
    ]
