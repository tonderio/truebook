"""
Parser for the monthly Tonder FEES file (`FEES_{MES}_{AÑO}_FINAL.xlsx`).

This is the spec v2 §2.3 input — produced by FinOps and uploaded by hand.
Distinct from `fees_processor.py` which computes fees from MongoDB
transactions; this parser ONLY reads the structured Excel file and
returns its rows in canonical form.

Sheet shapes (per spec §2.3 + observed real files):
  - "Detalle por Merchant"   header row 3  → per-merchant×concepto detail
  - "Resumen por Merchant"   header row 3  → per-merchant rollup
  - "Tonder Fees desglose diario" header row 2 → daily breakdown
  - "Resumen por Razon Social" header row 3 → per-legal-entity rollup

The parser auto-detects header rows (within the first 10) so minor
variants survive — the v2 spec says row 3, but the April template ships
with row 5 (different layout). Trust the data, not the spec literal.

Adquirente normalization: the file uses lowercase ('kushki', 'bitso',
'oxxopay', 'stp'). Sometimes blank or '—' for non-acquirer concepts
(Withdrawals, Settlements). We keep the source value verbatim and let
the caller decide grouping.
"""
from __future__ import annotations

import io
import logging
import math
import unicodedata
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ── column name → canonical key (Detalle por Merchant) ───────────────────

DETALLE_COLUMN_MAP: dict[str, str] = {
    "merchant": "merchant",
    "concepto": "concepto",
    "adquirente": "adquirente",
    "# eventos": "eventos",
    "eventos": "eventos",
    "monto procesado": "monto_procesado",
    "fee %": "fee_pct",
    "fee fijo": "fee_fijo",
    "total fee s/iva": "fee_siva",
    "total fee s iva": "fee_siva",
    "iva (16%)": "iva",
    "iva 16%": "iva",
    "iva": "iva",
    "total c/iva": "fee_civa",
    "total c iva": "fee_civa",
    "neto a liquidar": "neto_liquidar",
}

# Resumen por Merchant — different columns
RESUMEN_MERCHANT_COLUMN_MAP: dict[str, str] = {
    "merchant": "merchant",
    "monto procesado": "monto_procesado",
    "fees transacc.": "fees_transacc",
    "fees transacc": "fees_transacc",
    "other fees": "other_fees",
    "settlement": "settlement",
    "withdrawals": "withdrawals",
    "autorefunds": "autorefunds",
    "routing fee": "routing_fee",
    "total s/iva": "total_siva",
    "total s iva": "total_siva",
    "iva (16%)": "iva",
    "iva 16%": "iva",
    "iva": "iva",
    "total c/iva": "total_civa",
    "total c iva": "total_civa",
    "neto a liquidar": "neto_liquidar",
}

DAILY_COLUMN_MAP: dict[str, str] = {
    "fecha": "fecha",
    "merchant": "merchant",
    "concepto / operativa": "concepto",
    "concepto": "concepto",
    "# eventos": "eventos",
    "eventos": "eventos",
    "monto procesado": "monto_procesado",
    "fee s/iva": "fee_siva",
    "fee s iva": "fee_siva",
    "iva (16%)": "iva",
    "iva": "iva",
    "total c/iva": "fee_civa",
    "total c iva": "fee_civa",
}


def _norm(value: Any) -> str:
    s = str(value or "").strip().lower().replace("\n", " ")
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    return " ".join(s.split())


def _find_header_row(df: pd.DataFrame, must_contain: list[str], max_scan: int = 12) -> int | None:
    """Find the first row containing every term in must_contain (after normalization)."""
    needles = [_norm(t) for t in must_contain]
    scan = min(len(df.index), max_scan)
    for i in range(scan):
        cells = [_norm(v) for v in df.iloc[i].tolist() if str(v).strip() not in ("", "None", "nan")]
        if not cells:
            continue
        joined = " | ".join(cells)
        if all(n in joined for n in needles):
            return i
    return None


def _canonicalize(df: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    """Rename columns using the map; unknown columns kept as-is (lowercased, no accents)."""
    rename = {}
    for col in df.columns:
        norm = _norm(col)
        rename[col] = column_map.get(norm, norm)
    return df.rename(columns=rename)


def _to_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, float) and math.isnan(v):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s in ("—", "-", "nan", "None"):
        return 0.0
    s = s.replace("$", "").replace(",", "").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _drop_subtotal_rows(df: pd.DataFrame, key_col: str) -> pd.DataFrame:
    """Drop rows whose `key_col` value starts with 'Subtotal' / 'Total' / 'Suma'."""
    if key_col not in df.columns:
        return df
    mask = df[key_col].astype(str).apply(_norm).str.match(r"^(subtotal|total|suma|gran total)\b")
    if mask.any():
        logger.info("fees_parser: dropping %d aggregate row(s) from %s", mask.sum(), key_col)
    return df[~mask].copy()


# ── per-sheet parsers ────────────────────────────────────────────────────


def parse_detalle_por_merchant(content: bytes) -> list[dict]:
    """Sheet 'Detalle por Merchant' — one row per (merchant, concepto, adquirente)."""
    raw = pd.read_excel(io.BytesIO(content), sheet_name="Detalle por Merchant", header=None)
    header = _find_header_row(raw, ["merchant", "adquirente"])
    if header is None:
        logger.warning("fees_parser: no header row found in 'Detalle por Merchant'")
        return []

    df = pd.read_excel(io.BytesIO(content), sheet_name="Detalle por Merchant", header=header)
    df = _canonicalize(df, DETALLE_COLUMN_MAP)

    if "merchant" not in df.columns:
        logger.warning("fees_parser: 'merchant' column missing after canonicalization")
        return []

    df = df.dropna(subset=["merchant"])
    df = _drop_subtotal_rows(df, "merchant")

    # Normalize numeric columns
    for col in ("eventos", "monto_procesado", "fee_pct", "fee_fijo",
                "fee_siva", "iva", "fee_civa", "neto_liquidar"):
        if col in df.columns:
            df[col] = df[col].apply(_to_float)

    # Normalize string columns
    for col in ("merchant", "concepto", "adquirente"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # adquirente normalization: lowercase; '—' / blank / NaN → None
    def _norm_adq(v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        s = str(v).strip()
        if s in ("—", "-", "nan", "None", ""):
            return None
        return s.lower()

    if "adquirente" in df.columns:
        df["adquirente"] = df["adquirente"].apply(_norm_adq)

    return df.to_dict(orient="records")


def parse_resumen_por_merchant(content: bytes) -> list[dict]:
    """Sheet 'Resumen por Merchant' — per-merchant rollup."""
    try:
        raw = pd.read_excel(io.BytesIO(content), sheet_name="Resumen por Merchant", header=None)
    except (KeyError, ValueError):
        return []
    header = _find_header_row(raw, ["merchant", "monto procesado"])
    if header is None:
        return []

    df = pd.read_excel(io.BytesIO(content), sheet_name="Resumen por Merchant", header=header)
    df = _canonicalize(df, RESUMEN_MERCHANT_COLUMN_MAP)

    if "merchant" not in df.columns:
        return []
    df = df.dropna(subset=["merchant"])
    df = _drop_subtotal_rows(df, "merchant")

    numeric_cols = (
        "monto_procesado", "fees_transacc", "other_fees", "settlement",
        "withdrawals", "autorefunds", "routing_fee", "total_siva", "iva",
        "total_civa", "neto_liquidar",
    )
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(_to_float)
    df["merchant"] = df["merchant"].astype(str).str.strip()
    return df.to_dict(orient="records")


def parse_tonder_fees_diario(content: bytes) -> list[dict]:
    """Sheet 'Tonder Fees desglose diario' — daily breakdown rows."""
    sheet_name = "Tonder Fees desglose diario"
    try:
        raw = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name, header=None)
    except (KeyError, ValueError):
        return []
    header = _find_header_row(raw, ["fecha", "merchant"])
    if header is None:
        return []

    df = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name, header=header)
    df = _canonicalize(df, DAILY_COLUMN_MAP)

    if "fecha" not in df.columns:
        return []

    # Forward-fill the date column (the file uses a "date row" + multiple
    # merchant rows pattern: only the first row per date has the fecha)
    df["fecha"] = df["fecha"].astype(str).str.strip().replace({"nan": None, "None": None})
    df["fecha"] = df["fecha"].ffill()
    df = df.dropna(subset=["merchant"])

    for col in ("eventos", "monto_procesado", "fee_siva", "iva", "fee_civa"):
        if col in df.columns:
            df[col] = df[col].apply(_to_float)
    for col in ("merchant", "concepto"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df.to_dict(orient="records")


# ── top-level entry point ────────────────────────────────────────────────


def parse_fees_file(content: bytes, filename: str = "fees.xlsx") -> dict[str, Any]:
    """Parse a FEES_{MES}_{AÑO}_FINAL.xlsx file and return all four sheets.

    Returns:
        {
          "detalle":       [...],   # one row per (merchant, concepto, adquirente)
          "resumen":       [...],   # per-merchant rollup
          "diario":        [...],   # daily breakdown
          "totals_by_acquirer": {
              "kushki":   {"monto_procesado": ..., "fee_civa": ..., "neto_liquidar": ..., "eventos": ...},
              "bitso":    {...},
              "oxxopay":  {...},
              "stp":      {...},
              "other":    {...},   # adquirente is None / '—'
          },
          "totals_by_merchant_acquirer": {
              ("AFUNVIP", "bitso"): {monto_procesado, fee_civa, neto_liquidar, eventos},
              ...
          },
          "row_count": int,
        }
    """
    detalle = parse_detalle_por_merchant(content)
    resumen = parse_resumen_por_merchant(content)
    diario = parse_tonder_fees_diario(content)

    # Roll up by acquirer + by (merchant, acquirer) — needed for the v2 cuadre
    by_acq: dict[str, dict[str, float]] = {}
    by_merch_acq: dict[tuple[str, str], dict[str, float]] = {}

    for row in detalle:
        adq_raw = row.get("adquirente")
        adq = adq_raw if isinstance(adq_raw, str) and adq_raw else "other"
        merchant = row.get("merchant") or "unknown"

        for bucket in (
            by_acq.setdefault(adq, {}),
            by_merch_acq.setdefault((merchant, adq), {}),
        ):
            for k in ("monto_procesado", "fee_siva", "iva", "fee_civa", "neto_liquidar", "eventos"):
                bucket[k] = bucket.get(k, 0.0) + _to_float(row.get(k))

    # Round the rollups for nice display
    for d in by_acq.values():
        for k in d:
            d[k] = round(d[k], 2)
    for d in by_merch_acq.values():
        for k in d:
            d[k] = round(d[k], 2)

    return {
        "detalle": detalle,
        "resumen": resumen,
        "diario": diario,
        "totals_by_acquirer": by_acq,
        "totals_by_merchant_acquirer": {
            f"{m}|{a}": v for (m, a), v in by_merch_acq.items()
        },
        "row_count": len(detalle),
    }
