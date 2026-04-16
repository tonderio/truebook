"""
Kushki file parser.
Supports:
- Consolidated files (CSV/Excel) with daily and merchant summaries.
- Raw daily files from SFTP (sheet "Resumen" with headers after intro rows).
"""
import io
import logging
import unicodedata
from collections import defaultdict
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Expected column variants (normalized) -> canonical name
COLUMN_MAP = {
    "fecha": "date",
    "date": "date",
    "fecha liq": "date",
    "fecha liq.": "date",
    "fecha pago": "date",
    "fecha de pago": "date",
    "merchant": "merchant_name",
    "comercio": "merchant_name",
    "merchant name": "merchant_name",
    "merchant_name": "merchant_name",
    "transacciones": "tx_count",
    "transactions": "tx_count",
    "# txns": "tx_count",
    "txns": "tx_count",
    "cuenta de ticket_number": "tx_count",
    "cuenta de ticket number": "tx_count",
    "monto bruto": "gross_amount",
    "monto bruto (kushki)": "gross_amount",
    "gross": "gross_amount",
    "gross_amount": "gross_amount",
    "suma de approved_transaction_amount": "gross_amount",
    "bruto ajustes": "adjustments",
    "comision": "commission",
    "comision kushki": "kushki_commission",
    "com. kushki": "kushki_commission",
    "comision kushki + iva": "commission",
    "com. kushki + iva": "commission",
    "commission": "commission",
    "fee": "commission",
    "suma de kushki_commission": "kushki_commission",
    "suma de iva_kushki_commission": "iva_kushki_commission",
    "iva kushki": "iva_kushki_commission",
    "iva (16%)": "tonder_iva",
    "rolling reserve": "rolling_reserve",
    "rolling_reserve": "rolling_reserve",
    "rr retenido": "rolling_reserve",
    "suma de fraud_retention": "rolling_reserve",
    "rr liberado": "rr_released",
    "suma de liberacion de fondos": "rr_released",
    "devolucion (refund)": "refund",
    "contracargo (chargeback)": "chargeback",
    "cancelacion (void)": "void",
    "manual (manual)": "manual_adj",
    "ajustes": "adjustments",
    "suma de ajuste": "adjustments",
    "ajuste total": "adjustments",
    "deposito neto": "net_deposit",
    "deposito neto (monto abonar)": "net_deposit",
    "net deposit": "net_deposit",
    "net_deposit": "net_deposit",
    "deposito neto (abonar)": "net_deposit",
    "monto abonar": "net_deposit",
    "suma de monto abonar": "net_deposit",
    "com. tonder s/iva": "tonder_fee",
    "com. tonder c/iva": "tonder_fee_iva",
    "tasa efectiva": "effective_rate",
}


def _norm_text(value: Any) -> str:
    s = str(value or "").strip().lower().replace("\n", " ")
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = " ".join(s.split())
    return s


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in df.columns:
        normalized = _norm_text(col)
        canonical = COLUMN_MAP.get(normalized)
        if canonical:
            rename[col] = canonical
        else:
            rename[col] = normalized
    return df.rename(columns=rename)


def _find_header_row(raw: pd.DataFrame, max_scan_rows: int = 35) -> Optional[int]:
    scan = min(len(raw.index), max_scan_rows)
    for i in range(scan):
        row_values = [_norm_text(v) for v in raw.iloc[i].tolist() if str(v).strip() not in ("", "None", "nan")]
        if not row_values:
            continue
        joined = " | ".join(row_values)
        has_date = any(x in row_values for x in ("fecha de pago", "fecha liq.", "fecha liq", "fecha", "date"))
        has_amount = (
            "suma de monto abonar" in joined
            or "monto abonar" in joined
            or "deposito neto (abonar)" in joined
            or "net_deposit" in joined
            or "monto bruto" in joined
        )
        if has_date and has_amount:
            return i
    return None


def _parse_excel(content: bytes) -> pd.DataFrame:
    """Parse Excel, returning the best sheet. Also stores merchant sheet if found."""
    xls = pd.ExcelFile(io.BytesIO(content))
    preferred = ["Resumen Diario", "Resumen", "Detalle por Merchant", "Detalle de Liquidacion"]
    sheets = [s for s in preferred if s in xls.sheet_names] + [s for s in xls.sheet_names if s not in preferred]

    best_df = None
    best_score = -1
    for sheet in sheets:
        try:
            raw = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=None)
        except Exception:
            continue

        header_row = _find_header_row(raw)
        if header_row is None:
            header_row = 0

        try:
            df = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=header_row)
        except Exception:
            continue

        df = _normalize_columns(df)
        score = sum(1 for col in ("date", "net_deposit", "gross_amount", "merchant_name", "tx_count") if col in df.columns)

        if score > best_score:
            best_score = score
            best_df = df

    if best_df is not None:
        return best_df
    raise ValueError("Unable to identify a valid Kushki sheet")


def _parse_excel_multi(content: bytes):
    """Parse Excel returning both daily summary DF and merchant detail DF."""
    xls = pd.ExcelFile(io.BytesIO(content))
    daily_df = None
    merchant_df = None

    for sheet in xls.sheet_names:
        try:
            raw = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=None)
        except Exception:
            continue
        header_row = _find_header_row(raw)
        if header_row is None:
            continue
        try:
            df = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=header_row)
        except Exception:
            continue
        df = _normalize_columns(df)

        has_merchant = "merchant_name" in df.columns
        has_date = "date" in df.columns
        has_net = "net_deposit" in df.columns

        if has_merchant and has_date and has_net and merchant_df is None:
            merchant_df = df
        elif has_date and has_net and not has_merchant and daily_df is None:
            daily_df = df
        elif has_date and has_net and daily_df is None:
            daily_df = df

    return daily_df, merchant_df


def _parse_file(content: bytes, filename: str) -> pd.DataFrame:
    fname = filename.lower()
    if fname.endswith(".csv"):
        try:
            df = pd.read_csv(io.BytesIO(content), encoding="utf-8")
        except Exception:
            df = pd.read_csv(io.BytesIO(content), encoding="latin-1")
        return _normalize_columns(df)
    if fname.endswith((".xlsx", ".xls")):
        return _parse_excel(content)
    raise ValueError(f"Unsupported file type: {filename}")


def parse_kushki(content: bytes, filename: str) -> Dict[str, Any]:
    """
    Parse one Kushki file.
    Returns daily_summary and merchant_detail.
    For Excel files, extracts both daily and merchant sheets separately.
    """
    fname = filename.lower()
    merchant_df_extra = None

    if fname.endswith((".xlsx", ".xls")):
        daily_df, merchant_df_extra = _parse_excel_multi(content)
        df = daily_df if daily_df is not None else (merchant_df_extra if merchant_df_extra is not None else _parse_file(content, filename))
    else:
        df = _parse_file(content, filename)

    # Ensure required columns exist with defaults.
    for col in ["date", "tx_count", "gross_amount", "commission", "rolling_reserve", "net_deposit"]:
        if col not in df.columns:
            df[col] = 0

    # Helper: safely convert a column (or default) to numeric Series
    def _safe_numeric(col_or_val):
        if isinstance(col_or_val, pd.Series):
            return pd.to_numeric(col_or_val, errors="coerce").fillna(0)
        return pd.Series([0] * len(df), dtype=float)

    # Derive commission if only component fields exist.
    if "commission" not in df.columns or _safe_numeric(df["commission"]).sum() == 0:
        kushki_comm = _safe_numeric(df.get("kushki_commission", pd.Series()))
        iva_comm = _safe_numeric(df.get("iva_kushki_commission", pd.Series()))
        df["commission"] = kushki_comm + iva_comm

    # Rolling reserve net effect can include release columns in raw files.
    if "rr_released" in df.columns:
        retained = _safe_numeric(df.get("rolling_reserve", pd.Series()))
        released = _safe_numeric(df.get("rr_released", pd.Series()))
        df["rolling_reserve"] = retained - released

    # Convert numeric columns.
    numeric_cols = ["tx_count", "gross_amount", "commission", "rolling_reserve", "net_deposit"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # String normalize date column.
    df["date"] = df["date"].astype(str).str.strip()
    df = df[df["date"] != ""]
    if df.empty:
        return {
            "daily_summary": [],
            "merchant_detail": [],
            "total_net_deposit": 0.0,
            "row_count": 0,
        }

    # All numeric fields we want to aggregate
    ALL_NUM_FIELDS = [
        "tx_count", "gross_amount", "adjustments", "kushki_commission",
        "iva_kushki_commission", "commission", "rolling_reserve",
        "refund", "chargeback", "void", "manual_adj", "rr_released",
        "net_deposit", "tonder_fee", "tonder_iva", "tonder_fee_iva",
    ]

    # Ensure all numeric fields exist with defaults
    for col in ALL_NUM_FIELDS:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Daily summary with all fields.
    agg_dict = {col: (col, "sum") for col in ALL_NUM_FIELDS if col in df.columns}
    daily = df.groupby("date", as_index=False).agg(**agg_dict)
    daily_summary = daily.to_dict(orient="records")

    # Merchant detail — use separate merchant sheet if available.
    mdf = merchant_df_extra if merchant_df_extra is not None else (df if "merchant_name" in df.columns else None)
    merchant_detail = []
    merchant_daily_detail = []

    if mdf is not None and "merchant_name" in mdf.columns:
        mdf = mdf.copy()
        for col in ALL_NUM_FIELDS:
            if col not in mdf.columns:
                mdf[col] = 0.0
            else:
                mdf[col] = pd.to_numeric(mdf[col], errors="coerce").fillna(0)
        # Derive commission from components if needed
        if mdf["commission"].sum() == 0 and "kushki_commission" in mdf.columns:
            kc = pd.to_numeric(mdf.get("kushki_commission", pd.Series()), errors="coerce").fillna(0)
            iv = pd.to_numeric(mdf.get("iva_kushki_commission", pd.Series()), errors="coerce").fillna(0)
            mdf["commission"] = kc + iv

        # Aggregated per merchant (pivot)
        m_agg = {col: (col, "sum") for col in ALL_NUM_FIELDS if col in mdf.columns}
        merchant = mdf.groupby("merchant_name", as_index=False).agg(**m_agg)
        merchant_detail = merchant.to_dict(orient="records")

        # Raw per-merchant-per-day detail (the full 19-column view)
        if "date" in mdf.columns:
            mdf["date"] = mdf["date"].astype(str).str.strip()
            detail_cols = ["date", "merchant_name"] + [c for c in ALL_NUM_FIELDS if c in mdf.columns]
            merchant_daily_detail = mdf[detail_cols].to_dict(orient="records")

    total_net = float(daily["net_deposit"].sum())
    return {
        "daily_summary": daily_summary,
        "merchant_detail": merchant_detail,
        "merchant_daily_detail": merchant_daily_detail,
        "total_net_deposit": round(total_net, 6),
        "row_count": len(df),
    }


_MERGE_FIELDS = [
    "tx_count", "gross_amount", "adjustments", "kushki_commission",
    "iva_kushki_commission", "commission", "rolling_reserve",
    "refund", "chargeback", "void", "manual_adj", "rr_released",
    "net_deposit", "tonder_fee", "tonder_iva", "tonder_fee_iva",
]


def merge_kushki_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Consolidate multiple Kushki parsed outputs into a single clean monthly dataset.
    Merges all 16 numeric fields (not just the original 5).
    """
    def _new_acc():
        return {f: 0.0 for f in _MERGE_FIELDS}

    daily_acc = defaultdict(_new_acc)
    merchant_acc = defaultdict(_new_acc)
    all_daily_detail = []

    for result in results:
        for row in result.get("daily_summary", []) or []:
            date = str(row.get("date", "")).strip()
            if not date:
                continue
            for f in _MERGE_FIELDS:
                daily_acc[date][f] += float(row.get(f, 0) or 0)

        for row in result.get("merchant_detail", []) or []:
            merchant = str(row.get("merchant_name", "unknown")).strip() or "unknown"
            for f in _MERGE_FIELDS:
                merchant_acc[merchant][f] += float(row.get(f, 0) or 0)

        all_daily_detail.extend(result.get("merchant_daily_detail", []) or [])

    daily_summary = []
    for date, d in sorted(daily_acc.items(), key=lambda x: x[0]):
        entry = {"date": date}
        for f in _MERGE_FIELDS:
            entry[f] = int(round(d[f])) if f == "tx_count" else round(d[f], 6)
        daily_summary.append(entry)

    merchant_detail = []
    for merchant, d in sorted(merchant_acc.items(), key=lambda x: x[0].lower()):
        entry = {"merchant_name": merchant}
        for f in _MERGE_FIELDS:
            entry[f] = int(round(d[f])) if f == "tx_count" else round(d[f], 6)
        merchant_detail.append(entry)

    total_net = round(sum(r["net_deposit"] for r in daily_summary), 6)
    return {
        "daily_summary": daily_summary,
        "merchant_detail": merchant_detail,
        "merchant_daily_detail": all_daily_detail,
        "total_net_deposit": total_net,
    }
