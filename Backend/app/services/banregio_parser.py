"""
Banregio file parser.
Accepts PDF (bank statement) or Excel/CSV.
Produces movements list and summary.
Column H = deposit amount used for Kushki vs Banregio cross-check.
"""
import logging
import io
import re
from typing import Dict, Any, List
import pandas as pd

logger = logging.getLogger(__name__)


def _parse_pdf(content: bytes) -> pd.DataFrame:
    """Extract table data from Banregio PDF bank statement."""
    try:
        import pdfplumber
        rows = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if row:
                            rows.append(row)
        if not rows:
            return pd.DataFrame()

        # Use first non-empty row as header
        header = rows[0]
        data = rows[1:]
        df = pd.DataFrame(data, columns=header)
        return df
    except Exception as e:
        logger.error(f"PDF parse error: {e}")
        return pd.DataFrame()


def _find_header_row(raw: pd.DataFrame, max_scan: int = 20):
    """Scan for a row containing 'Fecha' + ('Cargo' or 'Abono') to use as header."""
    for i in range(min(len(raw), max_scan)):
        vals = [str(v).strip().lower() for v in raw.iloc[i].tolist() if str(v).strip() not in ("", "None", "nan")]
        has_fecha = any("fecha" in v for v in vals)
        has_amount = any(v in ("cargo", "abono", "abonos", "cargos", "monto") for v in vals)
        if has_fecha and has_amount:
            return i
    return None


def _parse_structured(content: bytes, filename: str) -> pd.DataFrame:
    fname = filename.lower()
    if fname.endswith(".csv"):
        # Banregio's CSV export from the bank's online portal has a
        # 9-row metadata preamble (account #, CLABE, address, RFC, ...)
        # with 1–3 comma-separated fields per row, then a 7-field header
        # at row 10. pandas's column-inference (any engine) trips on
        # this — the C engine raises ParserError, the Python engine
        # with on_bad_lines="skip" silently drops the 7-field rows.
        #
        # Phase 1 uses csv.reader directly (no column inference) just
        # to find the header row. Phase 2 uses pd.read_csv with the
        # detected header row, which makes the metadata preamble fall
        # outside the data section so column counts line up cleanly.
        import csv

        # Decode tolerantly — try utf-8 first, fall back to latin-1
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")

        rows = list(csv.reader(io.StringIO(text)))
        if rows:
            max_cols = max(len(r) for r in rows)
            padded = [r + [None] * (max_cols - len(r)) for r in rows]
            raw = pd.DataFrame(padded)
        else:
            raw = pd.DataFrame()

        header_row = _find_header_row(raw)
        if header_row is not None:
            try:
                return pd.read_csv(
                    io.BytesIO(content),
                    encoding="utf-8",
                    header=header_row,
                    engine="python",
                )
            except UnicodeDecodeError:
                return pd.read_csv(
                    io.BytesIO(content),
                    encoding="latin-1",
                    header=header_row,
                    engine="python",
                )

        # No identifiable header — return the raw padded DataFrame as
        # a last resort (parse_banregio's column-name lookup will fail
        # gracefully and yield 0 movements rather than crashing).
        return raw
    elif fname.endswith((".xlsx", ".xls")):
        # Scan all sheets for the best one with a valid header
        xls = pd.ExcelFile(io.BytesIO(content))
        for sheet in xls.sheet_names:
            raw = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=None)
            header_row = _find_header_row(raw)
            if header_row is not None:
                df = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=header_row)
                if len(df) > 0:
                    return df
        # Fallback: first sheet, pandas auto-detect
        return pd.read_excel(io.BytesIO(content))
    return pd.DataFrame()


def _clean_amount(val) -> float:
    import math
    if val is None:
        return 0.0
    s = str(val).replace(",", "").replace("$", "").strip()
    if not s or s.lower() in ("nan", "none", "", "-"):
        return 0.0
    try:
        v = float(s)
        return 0.0 if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return 0.0


def parse_banregio(content: bytes, filename: str) -> Dict[str, Any]:
    """
    Parse Banregio bank statement.
    Column H (index 7) = deposit amount for cross-check with Kushki col I.
    """
    fname = filename.lower()
    try:
        if fname.endswith(".pdf"):
            df = _parse_pdf(content)
        else:
            df = _parse_structured(content, filename)
    except Exception as e:
        # Surface the actual underlying error + a peek at the file
        # contents up the stack. Stage 6 catches this and writes it to
        # ProcessLog so FinOps can see *why* a file landed as 'error'
        # without needing to inspect the file by hand.
        logger.exception("Banregio parser failed for %s", filename)
        peek = content[:200].decode("utf-8", errors="replace") if content else "(empty)"
        raise ValueError(
            f"Banregio parser failed for {filename}: "
            f"{type(e).__name__}: {e}. First 200 bytes: {peek!r}"
        ) from e

    if df.empty:
        return {"movements": [], "summary": {}, "deposit_column": [], "row_count": 0}

    # Normalize columns
    df.columns = [str(c).strip() for c in df.columns]

    # Try to identify date, description, debit, credit columns (accent-insensitive)
    import unicodedata
    def _strip_accents(s):
        return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

    col_norm = {_strip_accents(c.lower()): c for c in df.columns}

    date_col = next((col_norm[k] for k in ["fecha", "date", "f. operacion"] if k in col_norm), df.columns[0] if len(df.columns) > 0 else None)
    desc_col = next((col_norm[k] for k in ["descripcion", "concepto", "description"] if k in col_norm), None)
    debit_col = next((col_norm[k] for k in ["cargo", "cargos", "debito", "debit"] if k in col_norm), None)
    credit_col = next((col_norm[k] for k in ["abono", "abonos", "credito", "credit", "deposito"] if k in col_norm), None)
    # Textual reference column — Banregio's online-portal CSV exposes a
    # 'Referencia' column with values like '_20260401400140BET…' that
    # the classifier's Tier-2 Kushki regex can match directly. The PDF
    # / older Excel exports may not have this column; in that case we
    # fall back to "" and rely on the description-side ref scan.
    ref_col = next(
        (col_norm[k] for k in ["referencia", "reference", "clave de rastreo", "clave rastreo"]
         if k in col_norm),
        None,
    )

    # Column H (index 7) is the numeric deposit reference column per the
    # original spec (used for Kushki ↔ Banregio amount cross-check).
    deposit_col_name = df.columns[7] if len(df.columns) > 7 else credit_col

    movements = []
    for _, row in df.iterrows():
        date_val = str(row[date_col]).strip() if date_col and date_col in row.index else ""
        desc_val = str(row[desc_col]).strip() if desc_col and desc_col in row.index else ""
        ref_val = str(row[ref_col]).strip() if ref_col and ref_col in row.index else ""
        debit_val = _clean_amount(row[debit_col]) if debit_col and debit_col in row.index else 0.0
        credit_val = _clean_amount(row[credit_col]) if credit_col and credit_col in row.index else 0.0
        dep_val = _clean_amount(row[deposit_col_name]) if deposit_col_name and deposit_col_name in row.index else 0.0

        # Skip garbage rows: no date, no amounts, or date is a header/summary text
        if date_val.lower() in ("", "nan", "none") or (debit_val == 0 and credit_val == 0 and dep_val == 0):
            continue
        # Skip rows where "date" is clearly not a date (e.g., summary text)
        if len(date_val) > 20:
            continue
        # Skip summary/total rows
        if date_val.upper().startswith("TOTAL") or "TOTAL" in date_val.upper():
            continue
        # Skip rows where description starts with TOTAL
        if desc_val.upper().startswith("TOTAL"):
            continue

        # Clean description / reference of "nan" sentinels
        if desc_val.lower() in ("nan", "none"):
            desc_val = ""
        if ref_val.lower() in ("nan", "none"):
            ref_val = ""

        movements.append({
            "date": date_val,
            "description": desc_val,
            "reference": ref_val,        # textual ref (e.g. '_20260401400140BET…')
            "debit": debit_val,
            "credit": credit_val,
            "deposit_ref": dep_val,      # numeric — used for amount cross-check only
        })

    total_credits = sum(m["credit"] for m in movements)
    total_debits = sum(m["debit"] for m in movements)
    deposit_refs = [m["deposit_ref"] for m in movements if m["deposit_ref"] > 0]

    summary = {
        "total_credits": round(total_credits, 6),
        "total_debits": round(total_debits, 6),
        "net": round(total_credits - total_debits, 6),
        "deposit_count": len(deposit_refs),
        "total_deposit_ref": round(sum(deposit_refs), 6),
    }

    return {
        "movements": movements,
        "summary": summary,
        "deposit_column": deposit_refs,  # Column H values for cross-check
        "row_count": len(movements),
    }
