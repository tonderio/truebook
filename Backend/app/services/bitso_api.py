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


def _extract_items_and_marker(data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Normalize Bitso SPEI v2 response shape. Real shape observed:
        { "deposits": [ {...}, {...} ], "next_page_token": "xxx" }
    Fallbacks kept for robustness.
    """
    if not isinstance(data, dict):
        return [], None

    # Real Bitso v2 SPEI shape — deposits at top level
    items = (
        data.get("deposits")
        or data.get("data")
        or data.get("items")
        or data.get("results")
        or []
    )
    marker = (
        data.get("next_page_token")
        or data.get("next")
        or data.get("marker")
        or data.get("next_marker")
    )

    # Legacy fallback: response wrapped in payload
    if not items and isinstance(data.get("payload"), (list, dict)):
        payload = data["payload"]
        if isinstance(payload, list):
            items = payload
        else:
            items = (
                payload.get("deposits")
                or payload.get("data")
                or payload.get("items")
                or []
            )
            if not marker:
                marker = (
                    payload.get("next_page_token")
                    or payload.get("next")
                    or payload.get("marker")
                )

    return items or [], marker


def _parse_iso_date(s: Optional[str]) -> Optional[str]:
    """Extract YYYY-MM-DD from an ISO timestamp string."""
    if not s or not isinstance(s, str) or len(s) < 10:
        return None
    return s[:10]


def download_monthly_deposits(year: int, month: int, page_limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch all SPEI deposits for the given month.

    Bitso's `/spei/v2/deposits` endpoint pagination uses `next_page_token`.
    Date filtering: we try a broad set of likely query-param names so this
    works regardless of which variant Bitso honors, and then filter
    client-side by `operation_date` to be safe.
    """
    start_date, end_date = _month_bounds(year, month)
    path = "/spei/v2/deposits"

    all_deposits: List[Dict[str, Any]] = []
    token: Optional[str] = None
    pages = 0

    while True:
        params: Dict[str, Any] = {
            # Try multiple date param conventions; API ignores unknown ones
            "operation_from": start_date,
            "operation_to": end_date,
            "start_date": start_date,
            "end_date": end_date,
            "limit": page_limit,
        }
        if token:
            # Bitso returns `next_page_token` in the response but expects
            # `page_token` in the request query string.
            params["page_token"] = token

        data = _request("GET", path, params=params)
        items, next_token = _extract_items_and_marker(data)

        if not items:
            break
        all_deposits.extend(items)
        pages += 1

        if not next_token:
            break
        token = next_token

        # Safety cap — accounts with very high volume
        if pages > 2000:
            logger.warning("Bitso: aborting pagination after 2000 pages")
            break

    # Client-side filter by operation_date in the target month
    # (covers cases where the API didn't honor date params server-side)
    target = f"{year:04d}-{month:02d}"
    filtered = []
    for d in all_deposits:
        op_date = _parse_iso_date(d.get("operation_date") or d.get("created_at"))
        if op_date and op_date.startswith(target):
            filtered.append(d)

    logger.info(
        "Bitso: fetched %d deposits across %d pages; %d in target month %s",
        len(all_deposits), pages, len(filtered), target,
    )
    return filtered


def test_connection() -> Dict[str, Any]:
    """
    Light connectivity check — fetches ONE page of deposits to verify the API
    call succeeds. Does not paginate.
    """
    if not is_configured():
        return {"ok": False, "error": "No configurado — faltan BITSO_API_KEY o BITSO_API_SECRET"}
    from datetime import datetime
    now = datetime.utcnow()
    try:
        start_date, end_date = _month_bounds(now.year, now.month)
        data = _request("GET", "/spei/v2/deposits", params={
            "start_date": start_date,
            "end_date": end_date,
            "limit": 1,
        })
        items, _ = _extract_items_and_marker(data)
        if items:
            sample = items[0]
            created = sample.get("created_at") or sample.get("fid") or "—"
            return {
                "ok": True,
                "message": f"Conexión exitosa. Cuenta Bitso con depósitos en {start_date[:7]}.",
                "sample_created_at": created,
            }
        return {"ok": True, "message": f"Conexión exitosa. Sin depósitos aún en {start_date[:7]}."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
