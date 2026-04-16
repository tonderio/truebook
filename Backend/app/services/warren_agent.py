"""
Warren AI Agent — Intelligent investigation of unclassified Banregio movements.

Warren uses Claude to analyze bank statement descriptions, cross-reference
against known patterns, and suggest classifications with confidence scores.
It acts as the fallback when the rule-based auto-classifier can't determine
the category.

Named after Warren Buffett — he always knows where every dollar went.
"""
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Known label taxonomy for Warren's context
VALID_LABELS = [
    "kushki_acquirer",
    "bitso_acquirer",
    "unlimit_acquirer",
    "pagsmile_acquirer",
    "stp_acquirer",
    "settlement_to_merchant",
    "revenue",
    "investment",
    "tax",
    "bank_expense",
    "currency_sale",
    "transfer_between_accounts",
]

LABEL_DESCRIPTIONS = {
    "kushki_acquirer": "Deposit from Kushki (card payment processor) via Santander. Usually contains 'KUSHKI' or CLABE 014180655075635651.",
    "bitso_acquirer": "Deposit from Bitso (crypto/SPEI processor) via NVIO bank. Usually contains 'NVIO' + CLABE 710969000046861948.",
    "unlimit_acquirer": "Deposit from Unlimit/Unlimint (card processor) via BBVA. Usually contains 'UNLIMINT' + CLABE 012180001260409691.",
    "pagsmile_acquirer": "Deposit from Pagsmile/OXXO Pay (cash payments) via Finco Pay. Usually contains 'FINCO PAY' or 'NEBULA NETWORK'.",
    "stp_acquirer": "Deposit from STP (SPEI network) as acquirer inbound. Contains 'LIQUIDACION' + 'TRES COMAS'.",
    "settlement_to_merchant": "Outbound SPEI transfer to a merchant (payout/dispersión). Contains merchant name + 'OUT' or 'SETTLEMENTS'.",
    "revenue": "Tonder's own revenue transfer. Goes to 'TONDER BBVA 2' CLABE 012580001199498360.",
    "investment": "Bank investment operation — apertura, pago capital, intereses, mesa de dinero.",
    "tax": "Tax withholding — ISR retention on investments.",
    "bank_expense": "Bank fee — 'Comisión Transferencia' SPEI fees and their IVA.",
    "currency_sale": "Foreign currency sale — 'Venta de Divisas'.",
    "transfer_between_accounts": "Transfer between Tonder's own bank accounts (e.g., Banregio ↔ BBVA).",
}

SYSTEM_PROMPT = """You are Warren, a FinOps AI agent for TrueBook (Tonder's reconciliation platform).

Your job is to classify unclassified Banregio bank statement movements into the correct category.

## Context
Tonder is a payment processor in Mexico. Their Banregio bank account receives deposits from acquirers (Kushki, Bitso, Unlimit, Pagsmile, STP) and sends settlements to merchants. Every movement must be classified.

## Valid Categories
{label_descriptions}

## Instructions
For each movement, analyze the description, reference, amount, and direction (cargo/abono) to determine the most likely category.

Respond with a JSON array of objects:
[
  {{
    "movement_index": 0,
    "suggested_label": "category_name",
    "confidence": 0.95,
    "reasoning": "Brief explanation of why this label"
  }}
]

Confidence scale:
- 0.9-1.0: Very confident — clear pattern match
- 0.7-0.89: Confident — likely correct but some ambiguity
- 0.5-0.69: Uncertain — could be multiple categories
- <0.5: Low confidence — needs human review

Only use categories from the valid list above. If truly unsure, use "unclassified" with low confidence."""


def build_warren_prompt(
    unclassified_movements: List[Dict[str, Any]],
) -> tuple:
    """Build the prompt for Warren to classify movements."""
    label_desc_text = "\n".join(
        f"- **{name}**: {desc}"
        for name, desc in LABEL_DESCRIPTIONS.items()
    )

    system = SYSTEM_PROMPT.format(label_descriptions=label_desc_text)

    movements_text = "## Movements to classify\n\n"
    for mov in unclassified_movements:
        direction = "IN (abono)" if mov.get("movement_type") == "abono" else "OUT (cargo)"
        movements_text += (
            f"### Movement {mov['movement_index']}\n"
            f"- Date: {mov.get('movement_date', 'N/A')}\n"
            f"- Description: {mov.get('movement_description', 'N/A')}\n"
            f"- Reference: {mov.get('reference', 'N/A')}\n"
            f"- Amount: ${abs(mov.get('movement_amount', 0)):,.2f} MXN ({direction})\n\n"
        )

    return system, movements_text


async def classify_with_warren(
    unclassified_movements: List[Dict[str, Any]],
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Use Claude to classify unclassified Banregio movements.

    Args:
        unclassified_movements: List of movement dicts with keys:
            movement_index, movement_date, movement_description,
            movement_amount, movement_type, reference
        api_key: Anthropic API key (reads from env if not provided)

    Returns:
        List of suggested classifications:
        [{movement_index, suggested_label, confidence, reasoning}]
    """
    if not unclassified_movements:
        return []

    # Get API key
    if not api_key:
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        logger.warning("Warren: No ANTHROPIC_API_KEY configured — skipping AI classification")
        return [{
            "movement_index": m["movement_index"],
            "suggested_label": "unclassified",
            "confidence": 0.0,
            "reasoning": "Warren AI agent not configured (missing ANTHROPIC_API_KEY)",
        } for m in unclassified_movements]

    system_prompt, user_prompt = build_warren_prompt(unclassified_movements)

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )

        if response.status_code != 200:
            logger.error(f"Warren: Claude API error {response.status_code}: {response.text[:200]}")
            return _fallback_response(unclassified_movements, "Claude API error")

        data = response.json()
        content = data.get("content", [{}])[0].get("text", "")

        # Parse JSON from response (handle markdown code blocks)
        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]

        suggestions = json.loads(json_str.strip())

        # Validate suggestions
        validated = []
        for s in suggestions:
            label = s.get("suggested_label", "unclassified")
            if label not in VALID_LABELS and label != "unclassified":
                label = "unclassified"
            validated.append({
                "movement_index": s.get("movement_index"),
                "suggested_label": label,
                "confidence": min(1.0, max(0.0, float(s.get("confidence", 0.5)))),
                "reasoning": s.get("reasoning", ""),
            })

        return validated

    except json.JSONDecodeError as e:
        logger.error(f"Warren: Failed to parse Claude response as JSON: {e}")
        return _fallback_response(unclassified_movements, "Failed to parse AI response")
    except Exception as e:
        logger.error(f"Warren: Error calling Claude API: {e}")
        return _fallback_response(unclassified_movements, str(e))


def classify_with_warren_sync(
    unclassified_movements: List[Dict[str, Any]],
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Synchronous wrapper for classify_with_warren."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If called from within an async context (FastAPI), use nest_asyncio or create task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    classify_with_warren(unclassified_movements, api_key),
                )
                return future.result(timeout=120)
        return loop.run_until_complete(
            classify_with_warren(unclassified_movements, api_key)
        )
    except RuntimeError:
        return asyncio.run(classify_with_warren(unclassified_movements, api_key))


def _fallback_response(
    movements: List[Dict[str, Any]],
    reason: str,
) -> List[Dict[str, Any]]:
    """Return unclassified suggestions when Warren can't process."""
    return [{
        "movement_index": m["movement_index"],
        "suggested_label": "unclassified",
        "confidence": 0.0,
        "reasoning": f"Warren fallback: {reason}",
    } for m in movements]
