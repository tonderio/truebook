"""
NaN-poisoning robustness tests for the classifier + bitso matcher paths.

Why this exists: pandas-derived dicts can carry float NaN as the value
of a string-typed key, and Python's truthy NaN bypasses naive `or`
fallbacks. We hit this on April 2026 — `auto_classify_all` got a NaN
in the `deposit_ref` field and crashed `unicodedata.normalize()` on
the first credit-side row, leaving 0 classifications stored. Stage 8's
exception handler caught it correctly, but the silent "0% coverage"
state was confusing for ops.

These tests poison every classifier-facing field with the full grid of
edge values (None, NaN, ±inf, int, float, money string, garbage string,
real string) and assert:

  1. Nothing raises.
  2. Real data still classifies correctly.
  3. Numeric values that masquerade as text are dropped, not stringified
     to "1234.56" which would garbage-match keyword rules.

Run with:  cd Backend && pytest tests/ -v
"""
from __future__ import annotations

import math
from datetime import date

import pytest

from app.services.auto_classifier import (
    auto_classify_all,
    classify_movement,
    compute_coverage,
)
from app.services.bitso_matcher import (
    _safe_float,
    _safe_str,
    build_adjustment_suggestion,
    find_candidates,
)


# ── Adversarial input grid ──────────────────────────────────────────────

# Values that are "truthy NaN" or weird numerics — all of these bypassed
# `... or ""` defaults in older code and produced TypeErrors deep inside
# unicodedata.normalize().
TRUTHY_NAN = float("nan")
TRUTHY_INF = float("inf")
NEG_INF = float("-inf")

# (label, value) pairs that any of these classifier fields might receive
NUMERIC_BAD = [
    ("None", None),
    ("nan", TRUTHY_NAN),
    ("inf", TRUTHY_INF),
    ("-inf", NEG_INF),
    ("zero_int", 0),
    ("zero_float", 0.0),
    ("nonzero_int", 42),
    ("nonzero_float", 186966.41),
    ("negative", -100.5),
]

STRING_INPUTS = [
    ("empty", ""),
    ("blank", "   "),
    ("nan_str", "nan"),
    ("None_str", "None"),
    ("real_kushki", "WXUP620 SPEI. SANTANDER. 014180655075635651. KUSHKI S DE RL DE CV. 20260401400140BET0000496549670"),
    ("real_pagsmile", "WXJM165 SPEI. FINCO PAY. 734180001300000005. NEBULA NETWORK"),
    ("real_bitso", "WYEK974 SPEI. NVIO. 710969000046861948. CAMPOBET"),
    ("real_settlement", "WZLE033 SPEI BCGAME OUT NUEVA"),
    ("unicode", "INVERSIÓN MESA DE DINERO"),
    ("with_accents", "Comisión de Transferencia"),
]


# ── auto_classifier — module-level helper sanity ────────────────────────


class TestAutoClassifierBasics:
    def test_classify_movement_with_string_inputs(self):
        """All real-shaped descriptions classify without raising."""
        for _, desc in STRING_INPUTS:
            cls, _, method = classify_movement(
                description=desc, reference=None, amount=100.0, movement_type="abono",
            )
            assert isinstance(cls, str)
            assert method == "auto"

    def test_classify_movement_handles_none_description(self):
        cls, _, _ = classify_movement(
            description=None, reference=None, amount=0, movement_type="cargo",
        )
        assert cls == "unclassified"


# ── auto_classify_all — the path that crashed in April ──────────────────


class TestAutoClassifyAllRobust:
    """Adversarial movement dicts — must never raise, must still classify
    the real-data items correctly even if neighbors are poisoned."""

    @pytest.mark.parametrize("bad_label,bad_value", NUMERIC_BAD)
    def test_numeric_in_description_field_does_not_crash(self, bad_label, bad_value):
        """Description holding a NaN/None/numeric (the April bug) — survive."""
        movs = [
            # Real data
            {"date": "01/04/2026", "description": "SPEI. NVIO. 710969000046861948", "credit": 100.0, "debit": 0},
            # Poisoned row in the middle
            {"date": "02/04/2026", "description": bad_value, "credit": 50.0, "debit": 0},
            # Real data again
            {"date": "03/04/2026", "description": "SPEI. FINCO PAY. 734180001300000005", "credit": 75.0, "debit": 0},
        ]
        out = auto_classify_all(movs)
        assert len(out) == 3
        assert out[0]["classification"] == "bitso_acquirer"
        assert out[2]["classification"] == "pagsmile_acquirer"

    @pytest.mark.parametrize("bad_label,bad_value", NUMERIC_BAD)
    def test_numeric_in_reference_field_does_not_crash(self, bad_label, bad_value):
        """The reference field used to receive a numeric deposit_ref →
        normalize() crash. Now coerced to '' for numerics."""
        movs = [
            {
                "date": "01/04/2026",
                "description": "SPEI. NVIO. 710969000046861948",
                "reference": bad_value,
                "deposit_ref": bad_value,
                "credit": 100.0,
                "debit": 0,
            },
        ]
        out = auto_classify_all(movs)
        assert out[0]["classification"] == "bitso_acquirer"

    def test_numeric_deposit_ref_is_dropped_not_stringified(self):
        """If we stringified a float deposit_ref we'd get e.g. '186966.41'
        which has no impact — but if a row had a float that LOOKS like a
        legacy ref code (e.g. 400140), str(float) could collide. Verify
        we drop numerics entirely from reference matching."""
        movs = [
            {
                "date": "01/04/2026",
                "description": "Random unrelated text",
                "reference": 0,                # the raw deposit_ref bug
                "deposit_ref": 186966.41,      # the actual April pattern
                "credit": 186966.41,
                "debit": 0,
            },
        ]
        out = auto_classify_all(movs)
        assert out[0]["classification"] == "unclassified"

    def test_kushki_ref_pattern_in_description_still_matches(self):
        """When reference field is empty but the Kushki regex pattern
        is embedded in the description — must still fire (Tier 2)."""
        movs = [
            {
                "date": "01/04/2026",
                "description": "WXUP620 SPEI. SANTANDER. ... 20260401400140BET0000496549670",
                "reference": None,
                "credit": 2758635.65,
                "debit": 0,
            },
        ]
        out = auto_classify_all(movs)
        assert out[0]["classification"] == "kushki_acquirer"

    def test_credit_is_nan_treated_as_zero(self):
        """NaN credit shouldn't be passed to comparison ops — coerce to 0."""
        movs = [
            {
                "date": "01/04/2026",
                "description": "Some description",
                "credit": TRUTHY_NAN,
                "debit": TRUTHY_NAN,
            },
        ]
        # Should classify (not raise); cargo with no amount is fine
        out = auto_classify_all(movs)
        assert len(out) == 1

    def test_april_fixture_full_coverage(self):
        """The exact description shapes from April's CSV — full path,
        no synthetic poisoning. Sanity check that real-world data still
        classifies cleanly after the defense."""
        movs = [
            # Acquirer deposits (5 — one per acquirer)
            {"description": "WXJM165 SPEI. FINCO PAY. 734180001300000005. NEBULA NETWORK", "credit": 186966.41, "debit": 0, "date": "01/04/2026"},
            {"description": "WXTA896 SPEI. STP. 646180567300000006. TRES COMAS SAPI DE CV LIQUIDACI?N STP CICLO", "credit": 32362.07, "debit": 0, "date": "01/04/2026"},
            {"description": "WXUP620 SPEI. SANTANDER. 014180655075635651. KUSHKI S DE RL", "credit": 2758635.65, "debit": 0, "date": "01/04/2026"},
            {"description": "WYEK974 SPEI. NVIO. 710969000046861948. CAMPOBET", "credit": 574152.74, "debit": 0, "date": "06/04/2026"},
            {"description": "WZIO285 SPEI. BBVA MEXICO. 012180001260409691. UNLIMINT MX SAPI", "credit": 18.90, "debit": 0, "date": "06/04/2026"},
            # Operational (4)
            {"description": "Pago Cap. de Inversión", "credit": 1500000.0, "debit": 0, "date": "01/04/2026"},
            {"description": "Ret. ISR de Inversion", "credit": 0, "debit": 423.50, "date": "01/04/2026"},
            {"description": "COM. SPEI", "credit": 0, "debit": 5.00, "date": "01/04/2026"},
            {"description": "Venta de Divisas", "credit": 0, "debit": 100000.0, "date": "01/04/2026"},
        ]
        out = auto_classify_all(movs)
        cov = compute_coverage(out)
        assert cov["unclassified"] == 0, f"Got: {cov}"
        # Every acquirer + operational category fired
        cls_set = {c["classification"] for c in out}
        assert "kushki_acquirer" in cls_set
        assert "bitso_acquirer" in cls_set
        assert "stp_acquirer" in cls_set
        assert "pagsmile_acquirer" in cls_set
        assert "unlimit_acquirer" in cls_set
        assert "investment" in cls_set
        assert "tax" in cls_set
        assert "bank_expense" in cls_set
        assert "currency_sale" in cls_set


# ── bitso_matcher — defensive coercion helpers ──────────────────────────


class TestBitsoMatcherSafeStr:
    def test_none_returns_empty(self):
        assert _safe_str(None) == ""

    def test_nan_returns_empty(self):
        assert _safe_str(TRUTHY_NAN) == ""

    def test_numeric_returns_empty(self):
        # Pure numerics aren't useful as text; drop them
        assert _safe_str(42) == ""
        assert _safe_str(186966.41) == ""

    def test_string_passthrough(self):
        assert _safe_str("CampoBet") == "CampoBet"
        assert _safe_str("  spaces  ") == "spaces"


class TestBitsoMatcherSafeFloat:
    def test_none_returns_zero(self):
        assert _safe_float(None) == 0.0

    def test_nan_inf_return_zero(self):
        assert _safe_float(TRUTHY_NAN) == 0.0
        assert _safe_float(TRUTHY_INF) == 0.0
        assert _safe_float(NEG_INF) == 0.0

    def test_numeric_passthrough(self):
        assert _safe_float(42) == 42.0
        assert _safe_float(123.45) == 123.45

    def test_money_string(self):
        assert _safe_float("$1,234.56") == 1234.56
        assert _safe_float("100.00") == 100.0

    def test_garbage_returns_zero(self):
        assert _safe_float("hello") == 0.0
        assert _safe_float("") == 0.0


# ── bitso_matcher — public API ──────────────────────────────────────────


class TestBitsoMatcherFindCandidates:
    @pytest.mark.parametrize("bad_label,bad_value", [
        ("nan", TRUTHY_NAN), ("None", None), ("inf", TRUTHY_INF),
    ])
    def test_nan_amount_returns_empty(self, bad_label, bad_value):
        line = {"net_amount": bad_value, "gross_amount": bad_value, "txn_date": date(2026, 4, 6)}
        result = find_candidates(
            bitso_line=line,
            banregio_movements=[
                {"date": "06/04/2026", "credit": 100.0, "debit": 0, "description": "test"},
            ],
            existing_classifications={},
            existing_matches=set(),
        )
        assert result == []

    def test_real_match_with_some_poisoned_neighbors(self):
        line = {"net_amount": 574152.74, "txn_date": date(2026, 4, 6)}
        movs = [
            {"date": "06/04/2026", "credit": TRUTHY_NAN, "debit": 0, "description": "poisoned"},
            {"date": "06/04/2026", "credit": 574152.74, "debit": 0, "description": TRUTHY_NAN},  # NaN desc
            {"date": TRUTHY_NAN,    "credit": 574152.74, "debit": 0, "description": "Real one"},
            {"date": "06/04/2026", "credit": 574152.74, "debit": 0, "description": "Real one"},
        ]
        result = find_candidates(
            bitso_line=line,
            banregio_movements=movs,
            existing_classifications={},
            existing_matches=set(),
        )
        # At least the two real-credit rows should match (NaN credit row gets skipped)
        assert len(result) >= 2
        # Every candidate has a string description (not NaN passed through)
        for c in result:
            assert isinstance(c["movement_description"], str)

    def test_existing_classifications_with_nan(self):
        """If `existing_classifications` map has a NaN value for some
        index, that movement should be treated as 'unclassified' and
        still considered for matching — the str-equality check used to
        silently exclude NaN values."""
        result = find_candidates(
            bitso_line={"net_amount": 100.0, "txn_date": date(2026, 4, 6)},
            banregio_movements=[
                {"date": "06/04/2026", "credit": 100.0, "debit": 0, "description": "test"},
            ],
            existing_classifications={0: TRUTHY_NAN},
            existing_matches=set(),
        )
        assert len(result) == 1


class TestBitsoMatcherBuildAdjustment:
    def test_nan_amounts_no_crash(self):
        out = build_adjustment_suggestion(
            bitso_amount=TRUTHY_NAN, banregio_amount=574152.74, process_id=1,
            merchant_name=TRUTHY_NAN,
        )
        assert out is not None
        # Description must not contain literal "$nan"
        assert "$nan" not in out["description"]
        # NaN merchant_name → None (don't store NaN in the DB)
        assert out["merchant_name"] is None

    def test_zero_delta_no_suggestion(self):
        out = build_adjustment_suggestion(
            bitso_amount=100.0, banregio_amount=100.0, process_id=1,
        )
        assert out is None

    def test_within_tolerance_no_suggestion(self):
        out = build_adjustment_suggestion(
            bitso_amount=100.0, banregio_amount=100.5, process_id=1,
            tolerance_amount=1.0,
        )
        assert out is None

    def test_real_delta_returns_suggestion(self):
        out = build_adjustment_suggestion(
            bitso_amount=100.0, banregio_amount=200.0, process_id=1,
            tolerance_amount=1.0, merchant_name="CampoBet",
        )
        assert out["amount"] == 100.0
        assert out["direction"] == "ADD"  # banco > bitso → ADD to received
        assert out["merchant_name"] == "CampoBet"
        assert "CampoBet" in out["description"]
