"""
Bitso report parser.

Parses Bitso settlement reports (CSV or Excel) into bitso_reports + bitso_report_lines.
Uses flexible column detection since Bitso report format may vary.
"""
import io
import logging
import unicodedata
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Column name variants → canonical name
COLUMN_MAP = {
    # Date columns
    "fecha": "txn_date",
    "date": "txn_date",
    "fecha deposito": "txn_date",
    "fecha de deposito": "txn_date",
    "fecha transaccion": "txn_date",
    "fecha operacion": "txn_date",
    "settlement date": "txn_date",
    "payment date": "txn_date",
    # Merchant
    "merchant": "merchant_name",
    "comercio": "merchant_name",
    "merchant name": "merchant_name",
    "nombre comercio": "merchant_name",
    "cliente": "merchant_name",
    # Amount columns
    "monto": "gross_amount",
    "amount": "gross_amount",
    "monto bruto": "gross_amount",
    "gross": "gross_amount",
    "gross amount": "gross_amount",
    "importe": "gross_amount",
    # Fee
    "fee": "fee_amount",
    "comision": "fee_amount",
    "commission": "fee_amount",
    "cargo": "fee_amount",
    # Net
    "neto": "net_amount",
    "net": "net_amount",
    "net amount": "net_amount",
    "monto neto": "net_amount",
    "deposito neto": "net_amount",
    "monto abonar": "net_amount",
    # Reference / ID
    "referencia": "txn_id",
    "reference": "txn_id",
    "id": "txn_id",
    "transaction id": "txn_id",
    "folio": "txn_id",
    "clabe": "txn_id",
    # Description
    "concepto": "description",
    "description": "description",
    "detalle": "description",
    "nota": "description",
    # Status
    "estado": "status",
    "status": "status",
    "estatus": "status",
}


def _norm_text(val: Any) -> str:
    """Normalize text: lowercase, strip, remove accents, collapse whitespace."""
    s = str(val).strip().lower()
    nfkd = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Remove newlines and extra whitespace
    s = " ".join(s.split())
    return s


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw column names to canonical names via COLUMN_MAP."""
    rename = {}
    for col in df.columns:
        normalized = _norm_text(col)
        canonical = COLUMN_MAP.get(normalized)
        if canonical:
            rename[col] = canonical
        else:
            rename[col] = normalized
    return df.rename(columns=rename)


def _find_header_row(raw: pd.DataFrame, max_scan_rows: int = 20) -> Optional[int]:
    """Scan for the header row by looking for date + amount column names."""
    scan = min(len(raw.index), max_scan_rows)
    date_tokens = {"fecha", "date", "fecha deposito", "fecha transaccion", "settlement date", "payment date"}
    amount_tokens = {"monto", "amount", "neto", "net", "gross", "importe", "monto bruto", "deposito neto"}

    for i in range(scan):
        row_values = [_norm_text(v) for v in raw.iloc[i].tolist()
                      if str(v).strip() not in ("", "None", "nan")]
        if not row_values:
            continue
        has_date = any(tok in row_values for tok in date_tokens)
        has_amount = any(tok in row_values for tok in amount_tokens)
        if has_date and has_amount:
            return i
    return None


def _parse_date(val: Any) -> Optional[date]:
    """Try to parse a date from various formats."""
    if val is None or str(val).strip() in ("", "nan", "None", "NaT"):
        return None
    if isinstance(val, (date, datetime)):
        return val if isinstance(val, date) else val.date()
    if isinstance(val, pd.Timestamp):
        return val.date()
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _safe_float(val: Any) -> float:
    """Convert to float, handling strings with commas and currency symbols."""
    if val is None or str(val).strip() in ("", "nan", "None", "-"):
        return 0.0
    s = str(val).replace(",", "").replace("$", "").replace(" ", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def parse_bitso(content: bytes, filename: str) -> Dict[str, Any]:
    """
    Parse a Bitso report file (CSV or Excel) into structured data.

    Returns:
        {
            "lines": [{txn_date, txn_id, merchant_name, gross_amount,
                        fee_amount, net_amount, description, status, raw_row}, ...],
            "total_amount": float,
            "period_start": date or None,
            "period_end": date or None,
        }
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "csv":
        df = _parse_csv(content)
    elif ext in ("xlsx", "xls"):
        df = _parse_excel(content)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Expected CSV or Excel.")

    if df is None or df.empty:
        raise ValueError("No data found in file after parsing")

    df = _normalize_columns(df)

    # Extract lines
    lines = []
    for idx, row in df.iterrows():
        raw_dict = {str(k): str(v) for k, v in row.to_dict().items()
                    if str(v).strip() not in ("", "nan", "None")}

        txn_date = _parse_date(row.get("txn_date"))
        gross = _safe_float(row.get("gross_amount", 0))
        fee = _safe_float(row.get("fee_amount", 0))
        net = _safe_float(row.get("net_amount", 0))

        # If only gross is provided, net = gross - fee
        if net == 0 and gross != 0:
            net = gross - fee

        # Skip rows with no meaningful amount
        if gross == 0 and net == 0:
            continue

        lines.append({
            "line_index": len(lines),
            "txn_date": txn_date,
            "txn_id": str(row.get("txn_id", "")).strip() or None,
            "merchant_name": str(row.get("merchant_name", "")).strip() or None,
            "gross_amount": round(gross, 2),
            "fee_amount": round(fee, 2),
            "net_amount": round(net, 2),
            "description": str(row.get("description", "")).strip() or None,
            "status": str(row.get("status", "")).strip() or None,
            "raw_row": raw_dict,
        })

    if not lines:
        raise ValueError("No valid data rows found in Bitso report")

    dates = [l["txn_date"] for l in lines if l["txn_date"]]
    total_amount = sum(l["net_amount"] for l in lines)

    return {
        "lines": lines,
        "total_amount": round(total_amount, 2),
        "period_start": min(dates) if dates else None,
        "period_end": max(dates) if dates else None,
    }


def _parse_csv(content: bytes) -> Optional[pd.DataFrame]:
    """Parse CSV with auto-detected delimiter and header row."""
    text = content.decode("utf-8", errors="replace")

    # Try common delimiters
    for sep in (",", ";", "\t", "|"):
        try:
            raw = pd.read_csv(io.StringIO(text), sep=sep, header=None,
                              dtype=str, keep_default_na=False)
            if raw.shape[1] < 2:
                continue

            header_row = _find_header_row(raw)
            if header_row is not None:
                df = pd.read_csv(io.StringIO(text), sep=sep, header=header_row,
                                 dtype=str, keep_default_na=False)
                if df.shape[1] >= 2:
                    return df

            # Fallback: use first row as header
            df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str,
                             keep_default_na=False)
            if df.shape[1] >= 2:
                return df
        except Exception:
            continue

    return None


def _parse_excel(content: bytes) -> Optional[pd.DataFrame]:
    """Parse Excel with best-sheet selection and header detection."""
    try:
        xls = pd.ExcelFile(io.BytesIO(content))
    except Exception as e:
        raise ValueError(f"Cannot open Excel file: {e}")

    best_df = None
    best_score = -1

    for sheet in xls.sheet_names:
        try:
            raw = pd.read_excel(io.BytesIO(content), sheet_name=sheet,
                                header=None, dtype=str)
        except Exception:
            continue

        header_row = _find_header_row(raw)
        if header_row is None:
            header_row = 0

        try:
            df = pd.read_excel(io.BytesIO(content), sheet_name=sheet,
                               header=header_row, dtype=str)
        except Exception:
            continue

        df = _normalize_columns(df)
        score = sum(1 for col in ("txn_date", "net_amount", "gross_amount",
                                   "merchant_name", "txn_id")
                    if col in df.columns)

        if score > best_score:
            best_score = score
            best_df = df

    return best_df
