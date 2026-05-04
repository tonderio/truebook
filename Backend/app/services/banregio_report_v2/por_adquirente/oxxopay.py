"""
OXXOPAY section of Sheet 2 (spec §4.2.4).

OXXOPay liquida vía Pagsmile — bank descriptions show 'SPEI PagSmile'.
Internally we classify these movements as `pagsmile_acquirer`; here we
display them as 'OXXOPay (vía Pagsmile)'.

Layout:
  banner '  OXXOPAY  —  N depósitos vía Pagsmile  —  $X MXN'
  SPEI list (Fecha, Descripción (banco), Monto Recibido)
  blank
  'Desglose por merchant (fuente: FEES_{MES}_{AÑO})'
  5-col merchant table (Merchant, # Eventos, Monto Procesado, Fee c/IVA, Neto a Liquidar)
  TOTAL OXXOPAY row
  Cuadre: Neto FEES / Recibido banco / Diferencia
"""
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
    fees_detalle_oxxopay: list[dict],
    period_label: str,
    umbral_minor: float,
) -> tuple[int, dict]:
    # Filter Banregio
    movs = []
    for idx, mov in enumerate(banregio_movements):
        cls = classifications_by_idx.get(idx)
        if cls and cls.classification == "pagsmile_acquirer":
            movs.append((idx, mov))

    n_deposits = len(movs)
    total_banco = sum(cm.to_float(mov.get("credit")) for _, mov in movs)

    # Banner
    banner = (
        f"  OXXOPAY  —  {n_deposits} depósitos vía Pagsmile  —  ${total_banco:,.2f} MXN"
    )
    row = cm.write_section_header(ws, start_row, banner, st.Fill.SECTION_OXXO)

    # SPEI list
    spei_rows = [
        (mov.get("date"), mov.get("description"), cm.to_float(mov.get("credit")))
        for _, mov in movs
    ]
    row = cm.write_spei_list(ws, row,
                             ("Fecha", "Descripción (banco)", "Monto Recibido"),
                             spei_rows)

    # Section header
    cm._set(ws, f"A{row}",
            f"Desglose por merchant (fuente: FEES_{period_label.replace(' ', '_').upper()})",
            fontobj=st.SECTION_FONT_BLUE, alignment=st.LEFT)
    row += 1

    # Merchant table headers
    headers = ["Merchant", "# Eventos", "Monto Procesado", "Fee c/IVA", "Neto a Liquidar"]
    for i, label in enumerate(headers):
        col = get_column_letter(i + 1)
        cm._set(ws, f"{col}{row}", label,
                fontobj=st.COL_HEADER_FONT,
                alignment=st.LEFT if i == 0 else st.RIGHT)
    row += 1

    # Aggregate FEES rows
    by_merchant: dict[str, dict] = {}
    for r in fees_detalle_oxxopay:
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

    # Sort by monto_procesado desc
    sorted_merchants = sorted(by_merchant.items(),
                              key=lambda x: -x[1]["monto_procesado"])

    total_eventos = 0
    total_monto = 0.0
    total_fee = 0.0
    total_neto = 0.0
    for merchant, v in sorted_merchants:
        cm._set(ws, f"A{row}", merchant, fontobj=st.BODY_FONT, alignment=st.LEFT)
        cm._set(ws, f"B{row}", int(v["eventos"]),
                fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_INT)
        cm._set(ws, f"C{row}", round(v["monto_procesado"], 2),
                fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_MXN)
        cm._set(ws, f"D{row}", round(v["fee_civa"], 2),
                fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_MXN)
        cm._set(ws, f"E{row}", round(v["neto_liquidar"], 2),
                fontobj=st.SECTION_FONT_BLUE, alignment=st.RIGHT, number_format=st.FMT_MXN)
        total_eventos += int(v["eventos"])
        total_monto += v["monto_procesado"]
        total_fee += v["fee_civa"]
        total_neto += v["neto_liquidar"]
        row += 1

    # TOTAL row
    cm._set(ws, f"A{row}", "TOTAL OXXOPAY",
            fontobj=st.BODY_BOLD, fillobj=st.fill(st.Fill.TOTAL), alignment=st.LEFT)
    cm._set(ws, f"C{row}", round(total_monto, 2),
            fontobj=st.BODY_BOLD, fillobj=st.fill(st.Fill.TOTAL),
            alignment=st.RIGHT, number_format=st.FMT_MXN)
    cm._set(ws, f"D{row}", round(total_fee, 2),
            fontobj=st.BODY_BOLD, fillobj=st.fill(st.Fill.TOTAL),
            alignment=st.RIGHT, number_format=st.FMT_MXN)
    cm._set(ws, f"E{row}", round(total_neto, 2),
            fontobj=st.BODY_BOLD, fillobj=st.fill(st.Fill.TOTAL),
            alignment=st.RIGHT, number_format=st.FMT_MXN)
    row += 1

    # Cuadre
    diff = total_neto - total_banco
    if abs(diff) <= 0.01:
        status_text, status_color = "✅ Cuadrado", st.C.GREEN_DARK
    elif abs(diff) <= umbral_minor:
        status_text, status_color = "🔍 Diferencia menor — en revisión", st.C.ORANGE
    else:
        status_text, status_color = f"⚠ Diff ${diff:,.2f}", st.C.ORANGE

    cm._set(ws, f"A{row}", "Neto FEES a liquidar", fontobj=st.BODY_FONT, alignment=st.LEFT)
    cm._set(ws, f"E{row}", round(total_neto, 2),
            fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_MXN)
    row += 1
    cm._set(ws, f"A{row}", "Recibido en banco (Pagsmile)",
            fontobj=st.BODY_FONT, alignment=st.LEFT)
    cm._set(ws, f"E{row}", round(total_banco, 2),
            fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_MXN)
    row += 1
    cm._set(ws, f"A{row}", "Diferencia",
            fontobj=st.BODY_BOLD, alignment=st.LEFT)
    cm._set(ws, f"E{row}", round(diff, 2),
            fontobj=st.font(size=10, color=status_color, bold=True),
            alignment=st.RIGHT, number_format=st.FMT_MXN)
    cm._set(ws, f"F{row}", status_text,
            fontobj=st.font(size=9, color=status_color, bold=True),
            alignment=st.LEFT)
    row += 1

    stats = {
        "n_deposits": n_deposits,
        "total_banco": round(total_banco, 2),
        "neto_fees": round(total_neto, 2),
        "diferencia": round(diff, 2),
        "status_text": status_text,
        "status_color": status_color,
    }
    return row + 1, stats
