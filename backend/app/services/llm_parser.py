"""
LLM-powered transaction parser.

Provider selection via config.llm_provider:
  "gemini"    → google-genai (default; gemini-2.0-flash)
  "anthropic" → anthropic SDK (claude-opus-4-7)
"""
import json
import logging
from typing import Optional

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

VALID_BROKERS = {"openbank", "trade_republic", "revolut", "degiro"}

SYSTEM_PROMPT = """\
You are a financial data parser. Extract investment transactions from raw text pasted by a user.

Return a JSON array. Each element must have exactly these fields:
- ticker: stock ticker (e.g. "AAPL", "VWCE.DE") or ISIN for Spanish mutual funds (e.g. "ES0170960015")
- asset_name: human-readable name if identifiable, otherwise null
- asset_type: "stock", "etf", or "fund" (use "fund" for ISINs and mutual funds)
- transaction_type: "buy" or "sell"
- date: ISO format YYYY-MM-DD
- shares: number of units (always positive)
- price: price per unit in native currency (if only total is given, compute price = total / shares)
- currency: 3-letter ISO code (e.g. "EUR", "USD"). Assume EUR if not mentioned.
- commission: broker fee in same currency as price. Use 0 if not mentioned.
- broker: one of openbank, trade_republic, revolut, degiro — or "other" if unclear
- notes: any relevant extra info, or null

Output ONLY the JSON array, no other text or markdown.
"""


class ParsedTransaction(BaseModel):
    ticker: str
    asset_name: Optional[str] = None
    asset_type: str = "stock"        # stock | etf | fund
    transaction_type: str = "buy"   # buy | sell
    date: str                        # YYYY-MM-DD
    shares: float
    price: float
    currency: str = "EUR"
    commission: float = 0.0
    broker: str = "other"
    notes: Optional[str] = None
    # Resolved by confirm endpoint / preview:
    asset_id: Optional[int] = None
    price_eur: Optional[float] = None
    commission_eur: Optional[float] = None


def parse_transactions(
    raw_text: str,
    broker_hint: Optional[str] = None,
) -> list[ParsedTransaction]:
    """Call the configured LLM to extract transactions from raw text."""
    hint_line = f"Broker hint: the data is from {broker_hint}.\n\n" if broker_hint else ""
    user_message = f"{hint_line}Raw transaction data:\n\n{raw_text}"

    provider = settings.llm_provider.lower()
    if provider == "gemini":
        raw = _call_gemini(user_message)
    elif provider == "anthropic":
        raw = _call_anthropic(user_message)
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Set to 'gemini' or 'anthropic'."
        )

    return _parse_response(raw)


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_gemini(user_message: str) -> str:
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not set in .env")

    model = settings.llm_model or "gemini-2.0-flash"
    client = genai.Client(api_key=settings.gemini_api_key)

    response = client.models.generate_content(
        model=model,
        contents=user_message,
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )
    return response.text


def _call_anthropic(user_message: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic not installed. Run: pip install anthropic")

    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set in .env")

    model = settings.llm_model or "claude-opus-4-7"
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(raw: str) -> list[ParsedTransaction]:
    text = raw.strip()
    # Strip markdown code fences if the model wrapped the JSON
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned invalid JSON: %s\nRaw: %.500s", exc, raw)
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

    if not isinstance(data, list):
        data = [data]

    results = []
    for item in data:
        try:
            results.append(ParsedTransaction(**item))
        except Exception as exc:
            logger.warning("Skipping malformed transaction row: %s — %s", item, exc)

    return results
