"""
Bitso SPEI v2 API client.

Fetches monthly incoming SPEI deposits from the Bitso Payouts & Funding API.
Mirrors the shape of `kushki_sftp.py` so `processes.py` can plug it in the
same way.

Reference:
  https://docs.bitso.com/bitso-payouts-funding/docs/spei-transactions-api-v1-to-v2-migration-guide

Auth: HMAC-SHA256
  Authorization: Bitso <api_key>:<nonce>:<signature>
  signature = HMAC_SHA256(api_secret, nonce + METHOD + REQUEST_PATH + body)
  nonce = monotonically-increasing integer (ms since epoch)
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class BitsoApiConfig:
    enabled: bool
    api_key: Optional[str]
    api_secret: Optional[str]
    base_url: str
    timeout_seconds: int


def _build_config() -> BitsoApiConfig:
    return BitsoApiConfig(
        enabled=settings.BITSO_API_ENABLED,
        api_key=settings.BITSO_API_KEY or None,
        api_secret=settings.BITSO_API_SECRET or None,
        base_url=(settings.BITSO_API_BASE_URL or "https://api.bitso.com").rstrip("/"),
        timeout_seconds=settings.BITSO_API_TIMEOUT_SECONDS,
    )


def is_configured() -> bool:
    cfg = _build_config()
    return bool(cfg.enabled and cfg.api_key and cfg.api_secret)


def _nonce() -> str:
    return str(int(time.time() * 1000))


def _sign(api_secret: str, nonce: str, method: str, path: str, body: str = "") -> str:
    """Build HMAC-SHA256 signature for a Bitso API request."""
    message = f"{nonce}{method}{path}{body}".encode("utf-8")
    return hmac.new(api_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _auth_header(api_key: str, api_secret: str, method: str, path: str, body: str = "") -> str:
    nonce = _nonce()
    signature = _sign(api_secret, nonce, method, path, body)
    return f"Bitso {api_key}:{nonce}:{signature}"


def _request(method: str, path: str, params: Optional[Dict[str, Any]] = None, body: str = "") -> Dict[str, Any]:
    """Make an authenticated request. Raises on HTTP errors."""
    cfg = _build_config()
    if not is_configured():
        raise RuntimeError("Bitso API is not configured (missing key/secret or disabled)")

    # The signature uses the full request path INCLUDING query string.
    query = ""
    if params:
        # Preserve key order to match the URL httpx builds
        query = "?" + "&".join(f"{k}={v}" for k, v in params.items())
    signed_path = f"{path}{query}"

    url = f"{cfg.base_url}{path}"
    headers = {
        "Authorization": _auth_header(cfg.api_key, cfg.api_secret, method, signed_path, body),
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=cfg.timeout_seconds) as client:
        resp = client.request(method, url, params=params, content=body or None, headers=headers)

    if resp.status_code >= 400:
        raise RuntimeError(f"Bitso API {method} {path} failed: {resp.status_code} {resp.text[:200]}")

    try:
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Bitso API returned invalid JSON: {e}")


def _month_bounds(year: int, month: int) -> Tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def download_monthly_deposits(year: int, month: int, page_limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch all SPEI deposits for the given month.

    Paginates through `/spei/v2/deposits` using the `marker` cursor until
    no more pages are returned.

    Returns the raw list of deposit objects as received from Bitso.
    """
    start_date, end_date = _month_bounds(year, month)
    path = "/spei/v2/deposits"

    all_deposits: List[Dict[str, Any]] = []
    marker: Optional[str] = None
    pages = 0

    while True:
        params: Dict[str, Any] = {
            "start_date": start_date,
            "end_date": end_date,
            "limit": page_limit,
        }
        if marker:
            params["marker"] = marker

        data = _request("GET", path, params=params)
        payload = data.get("payload") or data
        # Bitso typically wraps the list under payload.deposits or payload directly.
        items = payload.get("deposits") if isinstance(payload, dict) else payload
        if not items:
            break
        all_deposits.extend(items)
        pages += 1

        # Pagination: the response includes a "next" marker or similar.
        next_marker = None
        if isinstance(payload, dict):
            next_marker = payload.get("next") or payload.get("marker") or payload.get("next_marker")
        if not next_marker or len(items) < page_limit:
            break
        marker = next_marker

        # Safety cap — Bitso should have <50 pages/month at our volume.
        if pages > 200:
            logger.warning("Bitso: aborting pagination after 200 pages")
            break

    return all_deposits


def test_connection() -> Dict[str, Any]:
    """
    Light connectivity check — fetches the current month with limit=1.
    Returns a dict with { ok: bool, message|error, sample? }.
    """
    if not is_configured():
        return {"ok": False, "error": "No configurado — faltan BITSO_API_KEY o BITSO_API_SECRET"}
    from datetime import datetime
    now = datetime.utcnow()
    try:
        deposits = download_monthly_deposits(now.year, now.month, page_limit=1)
        if deposits:
            sample = deposits[0]
            created = sample.get("created_at") or sample.get("fid") or "—"
            return {
                "ok": True,
                "message": f"Conexión exitosa. {len(deposits)}+ depósito(s) en el mes actual",
                "sample_created_at": created,
            }
        return {"ok": True, "message": "Conexión exitosa. Sin depósitos aún en el mes actual."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
