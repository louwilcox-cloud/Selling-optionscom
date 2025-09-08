# options_fetcher.py
"""
Fetch a single-expiration options chain from Schwab and return a flat list of contracts.

Prereqs (in your project folder):
- pip install schwab-py python-dotenv
- .env file with:
    SCHWAB_API_KEY=YOUR_APP_KEY
    SCHWAB_APP_SECRET=YOUR_APP_SECRET
    SCHWAB_CALLBACK=https://127.0.0.1:8182/
    SCHWAB_TOKEN_PATH=token.json

Usage (from another script):
    from options_fetcher import get_chain_for_expiration
    rows = get_chain_for_expiration("TSLA", "2025-08-29")
    print(len(rows), "contracts")
"""

import os
from typing import Dict, Iterable, List, Optional
from datetime import date
from dotenv import load_dotenv
from schwab import auth


def _client():
    """
    Returns an authenticated Schwab client using env vars.
    Uses schwab-py's easy_client which handles token refresh automatically.
    """
    load_dotenv()
    api_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_APP_SECRET")
    callback = os.getenv("SCHWAB_CALLBACK", "https://127.0.0.1:8182/")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "token.json")

    missing = [k for k, v in {
        "SCHWAB_API_KEY": api_key,
        "SCHWAB_APP_SECRET": app_secret,
        "SCHWAB_CALLBACK": callback,
    }.items() if not v]
    if missing:
        raise RuntimeError(
            f"Missing env var(s): {missing}. Ensure your .env is present and filled in."
        )

    return auth.easy_client(
        api_key=api_key,
        app_secret=app_secret,
        callback_url=callback,
        token_path=token_path,
        # leave enforce_enums=True (default) so we use client enums below
    )


def _mid(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    try:
        if bid is None or ask is None:
            return None
        return (float(bid) + float(ask)) / 2.0
    except Exception:
        return None


def _flatten_side(
    side_map: Dict[str, Dict[str, List[dict]]],
    put_call: str,
    exp_map_key: str
) -> Iterable[dict]:
    """
    side_map example:
      {
        "2025-08-29:17": {
          "400.0": [ {contract}, ... ],
          "405.0": [ {contract}, ... ]
        }
      }
    """
    if not isinstance(side_map, dict):
        return []

    contracts_by_strike = side_map.get(exp_map_key, {})
    if not isinstance(contracts_by_strike, dict):
        return []

    for strike, contracts in contracts_by_strike.items():
        if not contracts:
            continue
        for c in contracts:
            yield {
                "putCall": put_call,                               # "CALL" | "PUT"
                "symbol": c.get("symbol"),
                "underlyingSymbol": c.get("underlyingSymbol"),
                "expirationDate": c.get("expirationDate"),          # milliseconds since epoch
                "daysToExpiration": c.get("daysToExpiration"),
                "strikePrice": c.get("strikePrice"),
                "bid": c.get("bid"),
                "ask": c.get("ask"),
                "last": c.get("last"),
                "mark": c.get("mark") if c.get("mark") is not None else _mid(c.get("bid"), c.get("ask")),
                "delta": c.get("delta"),
                "gamma": c.get("gamma"),
                "theta": c.get("theta"),
                "vega": c.get("vega"),
                "rho": c.get("rho"),
                "volatility": c.get("volatility"),                  # implied vol (e.g., 23.45)
                "openInterest": c.get("openInterest"),
                "totalVolume": c.get("totalVolume"),
                "theoreticalOptionValue": c.get("theoreticalOptionValue"),
                "theoreticalVolatility": c.get("theoreticalVolatility"),
                "inTheMoney": c.get("inTheMoney"),
                "percentChange": c.get("percentChange"),
            }


def _find_exp_map_key(map_obj: Dict[str, dict], ymd: str) -> str:
    """
    Schwab's exp maps use keys like 'YYYY-MM-DD:28' where the suffix is days-to-expiration.
    We match by startswith('YYYY-MM-DD').
    """
    if not isinstance(map_obj, dict):
        return ""
    for k in map_obj.keys():
        if isinstance(k, str) and k.startswith(ymd):
            return k
    return ""


def get_chain_for_expiration(
    symbol: str,
    expiration_ymd: str,
    strike_count: int = 250
) -> List[dict]:
    """
    Fetch the option chain for a single expiration date and return a flat list of contracts.

    Args:
        symbol: underlying ticker, e.g. "TSLA"
        expiration_ymd: "YYYY-MM-DD" for the specific expiry to pull
        strike_count: how many strikes around the money to request (both sides). Lower if payload is big.

    Returns:
        A list of dicts (CALLs and PUTs), each with normalized fields:
        putCall, symbol, underlyingSymbol, expirationDate, daysToExpiration,
        strikePrice, bid, ask, last, mark, delta, gamma, theta, vega, rho,
        volatility, openInterest, totalVolume, theoreticalOptionValue,
        theoreticalVolatility, inTheMoney, percentChange, underlyingPrice
    """
    c = _client()
    # Use enums from the client (avoids import issues)
    contract_type_enum = c.Options.ContractType.ALL

    # Schwab expects datetime.date for from_date/to_date
    exp_date = date.fromisoformat(expiration_ymd)

    # Keep payload modest with strike_count; you can tweak as needed
    r = c.get_option_chain(
        symbol.upper(),
        contract_type=contract_type_enum,
        include_underlying_quote=True,
        from_date=exp_date,
        to_date=exp_date,
        strike_count=strike_count,
    )
    r.raise_for_status()
    j = r.json()

    # Identify the exact exp map key (e.g., "2025-08-29:17")
    call_map = j.get("callExpDateMap") or {}
    put_map = j.get("putExpDateMap") or {}
    call_key = _find_exp_map_key(call_map, expiration_ymd)
    put_key = _find_exp_map_key(put_map, expiration_ymd)

    flat: List[dict] = []
    if call_key:
        flat.extend(_flatten_side(call_map, "CALL", call_key))
    if put_key:
        flat.extend(_flatten_side(put_map, "PUT", put_key))

    # Attach underlying price if present
    underlying_price: Optional[float] = None
    if isinstance(j.get("underlying"), dict):
        underlying_price = j["underlying"].get("last")
    elif j.get("underlyingPrice") is not None:
        underlying_price = j.get("underlyingPrice")

    for row in flat:
        row["underlyingPrice"] = underlying_price

    return flat


# Optional: run this file directly for a quick manual test.
if __name__ == "__main__":
    sym = input("Symbol: ").strip().upper()
    exp = input("Expiration (YYYY-MM-DD): ").strip()
    rows = get_chain_for_expiration(sym, exp)
    print(f"Fetched {len(rows)} contracts for {sym} {exp}.")
    for r in rows[:5]:
        keep = ("putCall", "strikePrice", "bid", "ask", "mark", "delta", "volatility", "openInterest", "totalVolume")
        print({k: r.get(k) for k in keep})