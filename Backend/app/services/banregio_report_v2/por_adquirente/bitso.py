"""
BITSO section of Sheet 2 (spec §4.2.3).

Layout:
  banner row '  BITSO  —  N depósitos  —  $X MXN  …'
  SPEI list (Fecha, Descripción, Monto Recibido)
  blank
  'Desglose por merchant'
  9-col header (Merchant, Rol, # Txns, Monto Procesado, Fee c/IVA,
                Neto a Liquidar, Recibido Banco, Diferencia, Estatus)
  Group separator: 'Grupo 1 — Tonder liquida usuarios desde Bitso (SPEI entran a Banregio)'
  G1 merchant rows (Recibido Banco / Diferencia / Estatus = '—' / 'Pago directo a usuarios')
  Group separator: 'Grupo 2 — Tonder repone saldo …'
  G2 merchant rows (real Recibido Banco for CampoBet, 0 for Artilu MX)
  TOTAL row (G2-only summed against banco)

Data sources:
  - Banregio movements where classification = bitso_acquirer  →  SPEI list
  - FEES file detalle rows where adquirente=bitso             →  per-merchant counts/amounts
  - banregio_report_config: bitso_grupo1, bitso_grupo2,
      pending_transfer_merchants, umbral_*
"""
from __future__ import annotations

from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .. import styles as st
from . import _common as cm


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def write(
    ws: Worksheet,
    start_row: int,
    *,
    banregio_movements: list[dict],
    classifications_by_idx: dict,
    fees_detalle_bitso: list[dict],   # rows from FEES detalle where adquirente=bitso
    bitso_grupo1: list[str],
    bitso_grupo2: list[str],
    pending_transfer_merchants: list[dict],   # [{merchant, source, ...}]
    umbral_minor: float,
    umbral_major: float,
) -> tuple[int, dict]:
    # ── Filter Banregio kushki_acquirer → bitso_acquirer ─────────────
    bitso_movs = []
    for idx, mov in enumerate(banregio_movements):
        cls = classifications_by_idx.get(idx)
        if cls and cls.classification == "bitso_acquirer":
            bitso_movs.append((idx, mov))

    n_deposits = len(bitso_movs)
    total_banco = sum(cm.to_float(mov.get("credit")) for _, mov in bitso_movs)

    # Banner
    banner = (
        f"  BITSO  —  {n_deposits} depósitos  —  ${total_banco:,.2f} MXN  "
        f"(solo CampoBet — Grupo 2)"
    )
    row = cm.write_section_header(ws, start_row, banner, st.Fill.SECTION_BITSO)

    # SPEI list
    spei_rows = [
        (mov.get("date"), mov.get("description"), cm.to_float(mov.get("credit")))
        for _, mov in bitso_movs
    ]
    row = cm.write_spei_list(ws, row,
                             ("Fecha", "Descripción", "Monto Recibido"),
                             spei_rows)

    # Desglose por merchant
    cm._set(ws, f"A{row}", "Desglose por merchant",
            fontobj=st.SECTION_FONT_BLUE, alignment=st.LEFT)
    row += 1

    headers = [
        "Merchant", "Rol", "# Txns", "Monto Procesado", "Fee c/IVA",
        "Neto a Liquidar", "Recibido Banco", "Diferencia", "Estatus",
    ]
    for i, label in enumerate(headers):
        col = get_column_letter(i + 1)
        cm._set(ws, f"{col}{row}", label,
                fontobj=st.COL_HEADER_FONT,
                alignment=st.LEFT if i in (0, 1, 8) else st.RIGHT)
    row += 1

    # Group merchants by configured G1/G2
    g1_set = {_norm(m) for m in bitso_grupo1}
    g2_set = {_norm(m) for m in bitso_grupo2}
    pending_set = {_norm(p.get("merchant", "")) for p in pending_transfer_merchants
                   if p.get("source") == "bitso"}

    # Aggregate FEES detalle rows by merchant
    by_merchant: dict[str, dict] = {}
    for r in fees_detalle_bitso:
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

    # Split into G1 / G2 / unclassified — write G1 first, G2 next
    def _bucket(name: str) -> str:
        n = _norm(name)
        if n in g1_set:
            return "g1"
        if n in g2_set:
            return "g2"
        return "other"

    g1_rows = [(m, v) for m, v in by_merchant.items() if _bucket(m) == "g1"]
    g2_rows = [(m, v) for m, v in by_merchant.items() if _bucket(m) == "g2"]
    other_rows = [(m, v) for m, v in by_merchant.items() if _bucket(m) == "other"]

    # G1 separator + rows
    if g1_rows:
        cm._set(ws, f"A{row}",
                "Grupo 1 — Tonder liquida usuarios desde Bitso (SPEI entran a Banregio)",
                fontobj=st.font(size=10, color=st.C.SUBTITLE, italic=True),
                alignment=st.LEFT)
        row += 1
        for merchant, v in sorted(g1_rows, key=lambda x: -x[1]["monto_procesado"]):
            _write_merchant_row(
                ws, row, merchant, "Liquida usuarios", v,
                recibido_banco=None, status_text="Pago directo a usuarios",
                status_color=st.C.SUBTITLE,
            )
            row += 1

    # G2 separator + rows
    if g2_rows:
        cm._set(ws, f"A{row}",
                "Grupo 2 — Tonder repone saldo CampoBet/Artilu (SPEI entran a Banregio)",
                fontobj=st.font(size=10, color=st.C.SUBTITLE, italic=True),
                alignment=st.LEFT)
        row += 1

    g2_total_neto = 0.0
    g2_total_recibido = 0.0
    g2_total_diff = 0.0

    for merchant, v in sorted(g2_rows, key=lambda x: -x[1]["monto_procesado"]):
        # CampoBet receives all banco SPEIs; Artilu MX receives 0 (pending)
        n = _norm(merchant)
        if n == "campobet":
            recibido = total_banco
        else:
            recibido = 0.0
        diff = v["neto_liquidar"] - recibido

        g2_total_neto += v["neto_liquidar"]
        g2_total_recibido += recibido
        g2_total_diff += diff

        is_pending = n in pending_set
        if is_pending and recibido == 0:
            status_text = "⚠️ Pendiente de transferir"
            status_color = st.C.RED
        elif abs(diff) <= 0.01:
            status_text = "✅ Cuadrado"
            status_color = st.C.GREEN_DARK
        elif abs(diff) > umbral_major:
            status_text = f"❓ En investigación (${abs(diff):,.2f})"
            status_color = st.C.ORANGE
        elif abs(diff) <= umbral_minor:
            status_text = "🔍 Diferencia menor"
            status_color = st.C.ORANGE
        else:
            status_text = f"⚠ ${diff:,.2f}"
            status_color = st.C.ORANGE

        _write_merchant_row(
            ws, row, merchant, "Repone saldo", v,
            recibido_banco=recibido, diff=diff,
            status_text=status_text, status_color=status_color,
        )
        row += 1

    # Unclassified merchants (warning per spec §8 validation)
    if other_rows:
        cm._set(ws, f"A{row}",
                f"Sin clasificar G1/G2 (revisar config): {', '.join(m for m, _ in other_rows)}",
                fontobj=st.font(size=9, color=st.C.ORANGE, italic=True),
                alignment=st.LEFT)
        row += 1

    # TOTAL BITSO (G2 only)
    if g2_rows:
        cm._set(ws, f"A{row}", "TOTAL BITSO (G2 vs Banco)",
                fontobj=st.BODY_BOLD, fillobj=st.fill(st.Fill.TOTAL), alignment=st.LEFT)
        cm._set(ws, f"F{row}", round(g2_total_neto, 2),
                fontobj=st.BODY_BOLD, fillobj=st.fill(st.Fill.TOTAL),
                alignment=st.RIGHT, number_format=st.FMT_MXN)
        cm._set(ws, f"G{row}", round(g2_total_recibido, 2),
                fontobj=st.BODY_BOLD, fillobj=st.fill(st.Fill.TOTAL),
                alignment=st.RIGHT, number_format=st.FMT_MXN)
        cm._set(ws, f"H{row}", round(g2_total_diff, 2),
                fontobj=st.BODY_BOLD, fillobj=st.fill(st.Fill.TOTAL),
                alignment=st.RIGHT, number_format=st.FMT_MXN)
        row += 1

    # Stats for resumen
    # Specifically expose CampoBet and Artilu MX since the resumen has
    # one row per merchant (spec §4.2.7).
    campo_neto = next((v["neto_liquidar"] for m, v in by_merchant.items()
                       if _norm(m) == "campobet"), 0.0)
    artilu_neto = next((v["neto_liquidar"] for m, v in by_merchant.items()
                        if _norm(m) == "artilu mx"), 0.0)

    stats = {
        "n_deposits": n_deposits,
        "total_banco": round(total_banco, 2),
        "campobet_neto_liquidar": round(campo_neto, 2),
        "campobet_recibido": round(total_banco, 2),
        "campobet_diferencia": round(campo_neto - total_banco, 2),
        "artilu_neto_liquidar": round(artilu_neto, 2),
        "artilu_recibido": 0.0,
        "artilu_diferencia": round(artilu_neto, 2),
    }
    return row + 1, stats


def _write_merchant_row(
    ws: Worksheet, row: int, merchant: str, rol: str, fees_agg: dict,
    *, recibido_banco: float | None = None, diff: float | None = None,
    status_text: str, status_color: str,
) -> None:
    """One Bitso merchant row (9 cols)."""
    cm._set(ws, f"A{row}", merchant, fontobj=st.BODY_FONT, alignment=st.LEFT)
    cm._set(ws, f"B{row}", rol,
            fontobj=st.font(size=9, color=st.C.SUBTITLE), alignment=st.LEFT)
    cm._set(ws, f"C{row}", int(fees_agg["eventos"]),
            fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_INT)
    cm._set(ws, f"D{row}", round(fees_agg["monto_procesado"], 2),
            fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_MXN)
    cm._set(ws, f"E{row}", round(fees_agg["fee_civa"], 2),
            fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_MXN)
    cm._set(ws, f"F{row}", round(fees_agg["neto_liquidar"], 2),
            fontobj=st.SECTION_FONT_BLUE, alignment=st.RIGHT, number_format=st.FMT_MXN)
    if recibido_banco is None:
        cm._set(ws, f"G{row}", "—",
                fontobj=st.font(size=10, color=st.C.SUBTITLE), alignment=st.RIGHT)
        cm._set(ws, f"H{row}", "—",
                fontobj=st.font(size=10, color=st.C.SUBTITLE), alignment=st.RIGHT)
    else:
        cm._set(ws, f"G{row}", round(recibido_banco, 2),
                fontobj=st.BODY_FONT, alignment=st.RIGHT, number_format=st.FMT_MXN)
        if diff is not None:
            color = st.C.RED if diff > 0.01 else st.C.GREEN_DARK if abs(diff) <= 0.01 else st.C.ORANGE
            cm._set(ws, f"H{row}", round(diff, 2),
                    fontobj=st.font(size=10, color=color, bold=True),
                    alignment=st.RIGHT, number_format=st.FMT_MXN)
    cm._set(ws, f"I{row}", status_text,
            fontobj=st.font(size=9, color=status_color, bold=True), alignment=st.LEFT)
