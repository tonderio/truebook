"""STP section of Sheet 2 (spec §4.2.5)."""
from __future__ import annotations

from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .. import styles as st
from . import _common as cm


def write(
    ws: Worksheet,
    start_row: int,
    *,
    banregio_movements: list[dict],
    classifications_by_idx: dict,
    fees_detalle_stp: list[dict],
    pending_transfer_merchants: list[dict],
    umbral_minor: float,
) -> tuple[int, dict]:
    movs = []
    for idx, mov in enumerate(banregio_movements):
        cls = classifications_by_idx.get(idx)
        if cls and cls.classification == "stp_acquirer":
            movs.append((idx, mov))

    n_deposits = len(movs)
    total_banco = sum(cm.to_float(mov.get("credit")) for _, mov in movs)
    word = "depósito" if n_deposits == 1 else "depósitos"

    banner = (
        f"  STP  —  {n_deposits} {word}  —  ${total_banco:,.2f} MXN recibidos"
    )
    row = cm.write_section_header(ws, start_row, banner, st.Fill.SECTION_STP)

    spei_rows = [
        (mov.get("date"), mov.get("description"), cm.to_float(mov.get("credit")))
        for _, mov in movs
    ]
    row = cm.write_spei_list(ws, row,
                             ("Fecha", "Descripción", "Monto Recibido"),
                             spei_rows)

    # Merchant table headers (5 cols same as OXXOPay)
    headers = ["Merchant", "# Eventos", "Monto Procesado", "Fee c/IVA", "Neto a Liquidar"]
    for i, label in enumerate(headers):
        col = get_column_letter(i + 1)
        cm._set(ws, f"{col}{row}", label,
                fontobj=st.COL_HEADER_FONT,
                alignment=st.LEFT if i == 0 else st.RIGHT)
    row += 1

    # Aggregate FEES rows
    by_merchant: dict[str, dict] = {}
    for r in fees_detalle_stp:
        merchant = str(r.get("merchant", "")).strip()
        if not merchant:
            continue
        agg = by_merchant.setdefault(merchant, {
            "eventos": 0, "monto_procesado": 0.0,
            "fee_civa": 0.0, "neto_liquidar": 0.0,
        })
        agg["eventos"] += int(cm.to_float(r.get("eventos")))
        agg["monto_procesado"] += cm.to_float(r.get("monto_procesado"))
        agg["fee_civa"] += cm.to_float(r.get("fee_civa"))
        agg["neto_liquidar"] += cm.to_float(r.get("neto_liquidar"))

    total_neto = 0.0
    for merchant, v in sorted(by_merchant.items(), key=lambda x: -x[1]["monto_procesado"]):
        cm._set(ws, f"A{row}", merchant, fontobj=st.BODY_FONT, alignment=st.LEFT)
        cm._set(ws, f"B{row}", int(v["eventos"]),
                fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_INT)
        cm._set(ws, f"C{row}", round(v["monto_procesado"], 2),
                fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_MXN)
        cm._set(ws, f"D{row}", round(v["fee_civa"], 2),
                fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_MXN)
        cm._set(ws, f"E{row}", round(v["neto_liquidar"], 2),
                fontobj=st.SECTION_FONT_BLUE, alignment=st.RIGHT, number_format=st.FMT_MXN)
        total_neto += v["neto_liquidar"]
        row += 1

    diff = total_neto - total_banco
    pending_set = {(p.get("merchant", "") or "").strip().lower()
                   for p in pending_transfer_merchants if p.get("source") == "stp"}

    stats = {
        "n_deposits": n_deposits,
        "total_banco": round(total_banco, 2),
        "neto_fees": round(total_neto, 2),
        "diferencia": round(diff, 2),
        "has_pending": bool(pending_set),
    }
    return row + 1, stats
