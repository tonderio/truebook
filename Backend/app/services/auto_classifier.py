"""
Auto-classification engine for Banregio movements.

Uses a 3-tier detection strategy:
  1. CLABE matching (most reliable — each acquirer deposits from a fixed bank account)
  2. Reference pattern matching (e.g., Kushki's _YYYYMMDD400140BET pattern)
  3. Description keyword matching (accent-insensitive, ordered by specificity)

Covers 12 movement categories identified from real March 2026 Banregio data:
  - 5 acquirer deposits: Kushki, Bitso (NVIO), Unlimit, Pagsmile (OXXO), STP
  - 7 operational categories: Settlement, Revenue, Investment, Tax, Bank Fees,
    Currency Sale, Inter-account Transfer
"""
import re
import unicodedata
from typing import List, Dict, Optional, Tuple


def _normalize(text: str) -> str:
    """Remove accents and normalize to uppercase ASCII for token matching."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).upper().strip()


# ═══════════════════════════════════════════════════════════════════════
# TIER 1: CLABE-based detection (most reliable)
# Each acquirer/entity deposits from a known CLABE. These are stable
# identifiers that don't change with description text variations.
# ═══════════════════════════════════════════════════════════════════════

CLABE_RULES: List[Tuple[str, Optional[str], List[str]]] = [
    # (classification, acquirer, [CLABE numbers])
    ("kushki_acquirer", "kushki", [
        "014180655075635651",       # Kushki via Santander (primary)
        "014180655095204512",       # Kushki via Santander — IT Business Partners MX
    ]),
    ("stp_acquirer", "stp", [
        "646180567300000006",       # STP via Banco STP
    ]),
    ("bitso_acquirer", "bitso", [
        "710969000046861948",       # Bitso via NVIO (own account receives)
    ]),
    ("unlimit_acquirer", "unlimit", [
        "012180001260409691",       # Unlimit via BBVA
    ]),
    ("pagsmile_acquirer", "pagsmile", [
        "734180001300000005",       # Pagsmile/Finco Pay
    ]),
    ("revenue", None, [
        "012580001199498360",       # Tonder revenue (BBVA)
    ]),
    ("transfer_between_accounts", None, [
        "012580001168262297",       # Tonder own BBVA account
    ]),
]

# ═══════════════════════════════════════════════════════════════════════
# TIER 2: Reference pattern matching
# ═══════════════════════════════════════════════════════════════════════

KUSHKI_REF_PATTERN = re.compile(r"_?\d{8}400140BET", re.IGNORECASE)

# ═══════════════════════════════════════════════════════════════════════
# TIER 3: Description keyword matching (ordered by specificity)
# More specific rules first to avoid false matches.
# ═══════════════════════════════════════════════════════════════════════

KEYWORD_RULES: List[Tuple[str, Optional[str], List[str]]] = [
    # ── Acquirer deposits (IN) ─────────────────────────────────────────
    ("kushki_acquirer", "kushki", [
        "KUSHKI S DE RL", "KUSHKI",
    ]),
    ("bitso_acquirer", "bitso", [
        # "NVIO" alone is too broad — "envío" (bank fee) contains it.
        # Use "SPEI. NVIO." (with delimiters) or rely on CLABE tier.
        "SPEI. NVIO.", "BITSO", "BITSO MEXICO", "BITSO HOLDINGS",
        "ALLVP", "FINTECIMAL", "CRYPTOBUYER",
        # CampoBet liquidations arrive via Bitso/NVIO as Abonos (credit)
        # to Banregio — these are acquirer deposits, not settlements.
        "SPEI CAMPOBET",
    ]),
    ("unlimit_acquirer", "unlimit", [
        "UNLIMINT MX SAPI", "UNLIMINT", "UNLIMIT",
    ]),
    ("pagsmile_acquirer", "pagsmile", [
        "FINCO PAY", "NEBULA NETWORK", "PAGSMILE", "OXXO PAY",
    ]),
    ("stp_acquirer", "stp", [
        # STP acquirer deposits are specific: STP + TRES COMAS + LIQUIDACION
        # Be careful: STP also appears in settlement outbound movements.
        # "LIQUIDACI" (prefix) catches both "LIQUIDACION" and the
        # encoding-mangled "LIQUIDACI?N" some bank exports produce.
        "LIQUIDACI",
        # April pattern: STP-side "TRASPASO STP PROCESAMIENTO PENDIENTE"
        # is an inbound STP deposit awaiting reconciliation.
        "TRASPASO STP",
    ]),

    # ── Settlements to merchants (OUT) ─────────────────────────────────
    # Rule: any SPEI Cargo (debit) with a known merchant name = settlement.
    # Settlements are money OUT — not reconciled against acquirers directly.
    # What matters for accountants: fees, tax, rolling reserve per merchant.
    ("settlement_to_merchant", None, [
        # Generic patterns
        "STP OUT", "OUT NUEVA", "SETTLEMENTS",
        # Known merchant names — these appear in "SPEI {MERCHANT} W{CODE}" format
        "SPEI BCGAME", "SPEI AFUN", "SPEI CAMPOBET", "SPEI GANGABET",
        "SPEI STRENDUS", "SPEI BETCRIS", "SPEI STADIOBET",
        "SPEI MOLINO", "SPEI TAJMAHAL", "SPEI GOLDEN",
        "SPEI VITAU", "SPEI VIVENTO", "SPEI ARTILU",
        "SPEI BIG BOLA", "SPEI HARD ROCK", "SPEI IDEM",
        "SPEI PESIX", "SPEI BRANZINO", "SPEI OBSIDIANA",
        "SPEI COQUETEOS", "SPEI ALAMO", "SPEI ESTADIO",
        "SPEI ONIX", "SPEI PUERTO", "SPEI RSN",
        # Legacy patterns
        "BCGAME OUT", "CAMPOBET OUT", "CAMPOBET STP", "GANGABET STP",
        "AFUN BANKAOL",
    ]),

    # ── Revenue / Transfer between accounts ──────────────────────────
    # "SPEI Revenue" is actually a transfer between Tonder's own accounts
    ("transfer_between_accounts", None, [
        "SPEI REVENUE", "REVENUE W", "TONDER BBVA", "TONDER BBV",
        "REEMBOLSO CAMBIO", "ABONO CAMBIO",
    ]),

    # ── Banking operations ─────────────────────────────────────────────

    # Bank transfer expenses FIRST (before Tax/Investment — "envío" contains
    # "NVIO" which would false-match Bitso, and must be caught early)
    ("bank_expense", None, [
        "COMISION TRANSFERENCIA", "IVA DE COMISION TRANSFERENCIA",
        "COMISION BANCARIA", "COMISION BANREGIO",
        "COM. SPEI", "COM SPEI", "IVA SPEI", "IVA DE COM",
        # Bank-side reversals — small refunds of a previously-charged
        # SPEI commission or a returned SPEI. Treat as bank_expense
        # (negative side) so they offset the original bank_expense.
        "DEVOLUCION   COMISION", "DEVOLUCION COMISION", "DEVOLUCION   SPEI",
        "DEVOLUCIÓN   COMISIÓN", "DEVOLUCIÓN COMISIÓN", "DEVOLUCIÓN   SPEI",
    ]),

    # Tax (before Investments — "ISR de Inversion" / "ISR Mesa Dinero" must match Tax)
    ("tax", None, [
        "RET. ISR", "RETENCION ISR", "RET ISR", "ISR DE INVERSION",
        "ISR MESA DINERO", "ISR MESA",
    ]),

    # Investments
    ("investment", None, [
        "INVERSION", "CAP. DE INVERSION", "INVERSIÓN",
        "PAGO CAP. DE INVERSION", "APERTURA DE INVERSION",
        "MESA DE DINERO", "INTERESES DE INV", "PAGO INTERESES",
        "INTERESES MESA DINERO", "INTERESES MESA",
    ]),

    # Currency sale
    ("currency_sale", None, [
        "VENTA DE DIVISAS",
    ]),

    # Transfer between own accounts
    ("transfer_between_accounts", None, [
        "TRES COMAS SAPI DE C V",
    ]),
]

# Settlement detection by reference pattern (058-DD/MM/YYYY — Tonder's dated ref)
SETTLEMENT_REF_PATTERN = re.compile(r"058-\d{2}/\d{2}/\d{4}", re.IGNORECASE)


def classify_movement(
    description: str,
    reference: Optional[str] = None,
    amount: Optional[float] = None,
    movement_type: Optional[str] = None,
) -> Tuple[str, Optional[str], str]:
    """
    Classify a single Banregio movement using 3-tier detection.

    Returns: (classification, acquirer, method)
        method is always 'auto' for rule-based classification.
    """
    desc_norm = _normalize(description or "")
    ref_norm = _normalize(reference or "")
    raw_desc = description or ""
    raw_ref = reference or ""

    # ── TIER 1: CLABE matching (most reliable) ─────────────────────────
    for classification, acquirer, clabes in CLABE_RULES:
        for clabe in clabes:
            if clabe in raw_desc or clabe in raw_ref:
                return classification, acquirer, "auto"

    # ── TIER 2: Reference pattern matching ─────────────────────────────
    # Some bank statement exports embed the reference inside the
    # description column (e.g. "20260416400140BET0000475090830") instead
    # of populating the dedicated reference column. Check both.
    if (raw_ref and KUSHKI_REF_PATTERN.search(raw_ref)) or (
        raw_desc and KUSHKI_REF_PATTERN.search(raw_desc)
    ):
        return "kushki_acquirer", "kushki", "auto"

    # Settlement detection by dated reference pattern (058-DD/MM/YYYY)
    if raw_ref and SETTLEMENT_REF_PATTERN.search(raw_ref):
        # Only if it's a cargo (outbound)
        if movement_type == "cargo" or (amount is not None and amount < 0):
            return "settlement_to_merchant", None, "auto"

    # ── TIER 3: Description keyword matching ───────────────────────────
    for classification, acquirer, tokens in KEYWORD_RULES:
        for token in tokens:
            if _normalize(token) in desc_norm:
                # Special guard: STP acquirer only on inbound (abono)
                if classification == "stp_acquirer":
                    if movement_type != "abono" and (amount is None or amount <= 0):
                        continue
                # Special guard: Bitso acquirer — merchant name tokens (CAMPOBET)
                # only match on Abono (credit). Cargo = settlement, handled below.
                if classification == "bitso_acquirer" and _normalize(token) in ("SPEI CAMPOBET",):
                    if movement_type != "abono" and (amount is None or amount <= 0):
                        continue
                # Special guard: Settlements only on outbound (cargo/debit)
                if classification == "settlement_to_merchant":
                    if movement_type != "cargo" and (amount is None or amount >= 0):
                        continue
                return classification, acquirer, "auto"

    # ── TIER 3b: Check reference for keyword patterns ──────────────────
    if ref_norm:
        for classification, acquirer, tokens in KEYWORD_RULES:
            for token in tokens:
                if _normalize(token) in ref_norm:
                    # Same guards as Tier 3
                    if classification == "stp_acquirer":
                        if movement_type != "abono" and (amount is None or amount <= 0):
                            continue
                    if classification == "settlement_to_merchant":
                        if movement_type != "cargo" and (amount is None or amount >= 0):
                            continue
                    return classification, acquirer, "auto"

    return "unclassified", None, "auto"


def auto_classify_all(
    movements: List[Dict],
) -> List[Dict]:
    """
    Classify all Banregio movements in bulk.

    Args:
        movements: List of movement dicts from BanregioResult.movements JSON.
            Expected keys: date, description, debit, credit, deposit_ref

    Returns:
        List of classification dicts ready for DB insertion.
    """
    results = []
    for idx, mov in enumerate(movements):
        desc = mov.get("description", "")
        ref = mov.get("deposit_ref", "") or mov.get("reference", "")
        credit = mov.get("credit") or 0
        debit = mov.get("debit") or 0
        amount = credit if credit else -debit
        mov_type = "abono" if credit else "cargo"

        classification, acquirer, method = classify_movement(
            description=desc,
            reference=ref,
            amount=amount,
            movement_type=mov_type,
        )

        results.append({
            "movement_index": idx,
            "movement_date": mov.get("date", ""),
            "movement_description": desc,
            "movement_amount": amount,
            "movement_type": mov_type,
            "classification": classification,
            "acquirer": acquirer,
            "classification_method": method,
        })

    return results


def compute_coverage(classifications: List[Dict]) -> Dict:
    """Compute Banregio coverage stats from a list of classifications."""
    total = len(classifications)
    if total == 0:
        return {
            "total_movements": 0,
            "classified": 0,
            "unclassified": 0,
            "ignored": 0,
            "coverage_pct": 0.0,
            "by_classification": {},
        }

    by_class = {}
    unclassified = 0
    ignored = 0

    for c in classifications:
        cls_name = c.get("classification", "unclassified")
        by_class[cls_name] = by_class.get(cls_name, 0) + 1
        if cls_name == "unclassified":
            unclassified += 1
        elif cls_name == "ignored":
            ignored += 1

    classified = total - unclassified
    coverage_pct = round((classified / total) * 100, 2) if total > 0 else 0.0

    return {
        "total_movements": total,
        "classified": classified,
        "unclassified": unclassified,
        "ignored": ignored,
        "coverage_pct": coverage_pct,
        "by_classification": by_class,
    }
