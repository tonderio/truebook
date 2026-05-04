"""UNLIMIT section of Sheet 2 (spec §4.2.6).

Unlimit doesn't generate new processed amount each month — every SPEI
received is purely a Rolling Reserve release. monto_procesado=0,
diferencia=0 always.
"""
from __future__ import annotations

from openpyxl.worksheet.worksheet import Worksheet

from .. import styles as st
from . import _common as cm


def write(
    ws: Worksheet,
    start_row: int,
    *,
    banregio_movements: list[dict],
    classifications_by_idx: dict,
) -> tuple[int, dict]:
    movs = []
    for idx, mov in enumerate(banregio_movements):
        cls = classifications_by_idx.get(idx)
        if cls and cls.classification == "unlimit_acquirer":
            movs.append((idx, mov))

    n_deposits = len(movs)
    total_banco = sum(cm.to_float(mov.get("credit")) for _, mov in movs)
    word = "depósito" if n_deposits == 1 else "depósitos"

    banner = (
        f"  UNLIMIT  —  {n_deposits} {word}  —  ${total_banco:,.2f} MXN  "
        f"|  Todo Rolling Reserve liberado"
    )
    row = cm.write_section_header(ws, start_row, banner, st.Fill.SECTION_UNLIMIT)

    spei_rows = [
        (mov.get("date"), mov.get("description"), cm.to_float(mov.get("credit")))
        for _, mov in movs
    ]
    row = cm.write_spei_list(ws, row,
                             ("Fecha", "Descripción", "Monto (RR Liberado)"),
                             spei_rows)

    # TOTAL row
    cm._set(ws, f"A{row}", "TOTAL UNLIMIT",
            fontobj=st.BODY_BOLD, fillobj=st.fill(st.Fill.TOTAL), alignment=st.LEFT)
    cm._set(ws, f"C{row}", round(total_banco, 2),
            fontobj=st.BODY_BOLD, fillobj=st.fill(st.Fill.TOTAL),
            alignment=st.RIGHT, number_format=st.FMT_MXN)
    cm._set(ws, f"D{row}", "✅ Todo RR liberado — sin procesado",
            fontobj=st.font(size=9, color=st.C.GREEN_DARK, bold=True),
            fillobj=st.fill(st.Fill.TOTAL), alignment=st.LEFT)
    row += 1

    stats = {
        "n_deposits": n_deposits,
        "total_banco": round(total_banco, 2),
    }
    return row + 1, stats
