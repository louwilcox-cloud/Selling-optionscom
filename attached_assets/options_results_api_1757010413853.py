#!/usr/bin/env python3
"""
Flask API (and optional CLI) that fetches an options chain for a given
symbol and expiration, then computes the same fields as your Access
Results_Both_WithType chain (includes Type and totals across BOTH types).

Endpoints:
  GET /api/quote?symbol=NVDA
  GET /api/get_options_data?symbol=NVDA
  GET /api/get_options_data?symbol=NVDA&date=2025-08-29
  GET /api/results_both?symbol=NVDA&date=2025-08-29
  GET /api/prediction?symbol=NVDA&date=2025-08-29

CLI:
  python options_results_api.py NVDA 2025-08-29
"""

from __future__ import annotations

import os
import sys
import math
from typing import Any

from flask import Flask, request, jsonify
import pandas as pd
import yfinance as yf

app = Flask(__name__)

# ------------------ helpers ------------------

def _safe_float(x) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return 0.0
        return float(x)
    except Exception:
        return 0.0

def _to_rows(df: pd.DataFrame, type_label: str):
    cols = ["strike", "lastPrice", "volume", "openInterest"]
    present = [c for c in cols if c in df.columns]
    out = []
    for _, r in df[present].iterrows():
        out.append({
            "strike": _safe_float(r.get("strike", 0)),
            "lastPrice": _safe_float(r.get("lastPrice", 0)),
            "volume": int(_safe_float(r.get("volume", 0))),
            "openInterest": int(_safe_float(r.get("openInterest", 0))),
            "type": type_label,
        })
    return out

def _fetch_expirations(symbol: str):
    t = yf.Ticker(symbol)
    exps = t.options or []
    return [str(e) for e in exps]

def _fetch_chain(symbol: str, date: str):
    t = yf.Ticker(symbol)
    chain = t.option_chain(date)
    calls_df = chain.calls.copy()
    puts_df = chain.puts.copy()
    calls = _to_rows(calls_df, "Call")
    puts = _to_rows(puts_df, "Put")
    return calls, puts

def _compute_results(symbol: str, exp_date: str, calls, puts):
    """
    Weighted BreakEven across Calls + Puts.

    For Calls: BE = Strike + premium
    For Puts:  BE = Strike - premium
    Weight = premium * OI
    """
    all_rows = []
    for src, type_label in [(calls, "Call"), (puts, "Put")]:
        for r in src:
            strike = _safe_float(r.get("strike", 0))
            last_price = _safe_float(r.get("lastPrice", 0))
            oi = int(_safe_float(r.get("openInterest", 0)))

            avg_last = last_price
            if type_label == "Call":
                breakeven = strike + avg_last   # BE_call
            else:
                breakeven = strike - avg_last   # BE_put

            tot_pre = avg_last * oi

            all_rows.append({
                "Symbol": symbol,
                "Strike": strike,
                "Exp Date": exp_date,
                "AvgLast": avg_last,
                "BreakEven": breakeven,
                "CountOfSymbol": 1,
                "OI": oi,
                "TotPre": tot_pre,
                "Type": type_label
            })

    sum_of_tot_pre = sum(r["TotPre"] for r in all_rows) or 0.0

    rows = []
    for r in all_rows:
        pct = (r["TotPre"] / sum_of_tot_pre) if sum_of_tot_pre > 0 else 0.0
        part = r["BreakEven"] * pct
        row = dict(r)
        row["SumOfTotPre"] = sum_of_tot_pre
        row["PercentofMoneySpent"] = pct
        row["PartofMoney"] = part
        rows.append(row)

    rows.sort(key=lambda x: (x["Strike"], 0 if x["Type"] == "Call" else 1))
    return {
        "symbol": symbol,
        "expDate": exp_date,
        "rows": rows,
        "sumPartOfMoney": sum(r["PartofMoney"] for r in rows),
        "sumOfTotPre": sum_of_tot_pre,
        "countRows": len(rows),
    }

def _get_quote_price(symbol: str) -> float:
    t = yf.Ticker(symbol)
    price = None
    try:
        price = t.fast_info.get("last_price", None)
    except Exception:
        price = None
    if price is None:
        hist = t.history(period="1d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
    return _safe_float(price)

# ------------------ endpoints ------------------

@app.get("/api/quote")
def api_quote():
    symbol = (request.args.get("symbol") or "").strip().upper()
    if not symbol:
        return jsonify({"error": "Missing 'symbol'"}), 400
    try:
        price = _get_quote_price(symbol)
        if price <= 0:
            raise ValueError("No price found")
        return jsonify({"symbol": symbol, "price": round(price, 4)})
    except Exception as e:
        return jsonify({"error": f"Quote fetch failed: {e}"}), 500

@app.get("/api/get_options_data")
def api_get_options_data():
    symbol = (request.args.get("symbol") or "").strip().upper()
    date = request.args.get("date")

    if not symbol:
        return jsonify({"error": "Missing 'symbol'"}), 400

    if not date:
        try:
            expirations = _fetch_expirations(symbol)
            return jsonify(expirations)
        except Exception as e:
            return jsonify({"error": f"Failed to fetch expirations: {e}"}), 500

    try:
        calls, puts = _fetch_chain(symbol, date)
        return jsonify({"symbol": symbol, "date": date, "calls": calls, "puts": puts})
    except Exception as e:
        return jsonify({"error": f"Failed to fetch options chain: {e}"}), 500

@app.get("/api/results_both")
def api_results_both():
    symbol = (request.args.get("symbol") or "").strip().upper()
    date = (request.args.get("date") or "").strip()

    if not symbol or not date:
        return jsonify({"error": "Provide both 'symbol' and 'date' (YYYY-MM-DD)"}), 400

    try:
        calls, puts = _fetch_chain(symbol, date)
        results = _compute_results(symbol, date, calls, puts)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": f"Computation failed: {e}"}), 500

@app.get("/api/prediction")
def api_prediction():
    """
    Returns only the essentials for the UI:
      - ok flag
      - symbol, expDate
      - currentPrice
      - predictedPrice (sum of PartofMoney across Calls+Puts)
      - pctChange (predicted vs current)
    """
    symbol = (request.args.get("symbol") or "").strip().upper()
    date = (request.args.get("date") or "").strip()
    if not symbol or not date:
        return jsonify({"ok": False, "error": "Provide both 'symbol' and 'date' (YYYY-MM-DD)"}), 400
    try:
        calls, puts = _fetch_chain(symbol, date)
        calc = _compute_results(symbol, date, calls, puts)
        predicted = float(calc["sumPartOfMoney"]) if calc else 0.0
        current = _get_quote_price(symbol)
        pct = (predicted - current) / current if current > 0 else 0.0
        return jsonify({
            "ok": True,
            "symbol": symbol,
            "expDate": date,
            "currentPrice": current,
            "predictedPrice": predicted,
            "pctChange": pct
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Prediction failed: {e}"}), 500

# ------------------ cli or server ------------------

def _rows_to_dataframe(rows):
    order = [
        "Symbol", "Strike", "Exp Date", "AvgLast", "BreakEven",
        "CountOfSymbol", "OI", "TotPre", "Type", "SumOfTotPre",
        "PercentofMoneySpent", "PartofMoney"
    ]
    df = pd.DataFrame(rows)
    for col in order:
        if col not in df.columns:
            df[col] = None
    return df[order]

def run_cli(symbol: str, date: str) -> None:
    calls, puts = _fetch_chain(symbol, date)
    results = _compute_results(symbol, date, calls, puts)
    df = _rows_to_dataframe(results["rows"])
    with pd.option_context("display.max_rows", None, "display.max_columns", None, "display.width", 180):
        print(df.to_string(index=False))
    out_csv = f"results_both_{symbol}_{date}.csv".replace("/", "-")
    df.to_csv(out_csv, index=False)
    print(f"\nSaved: {out_csv}")
    print(f"SumOfTotPre: {results['sumOfTotPre']:.2f}")
    print(f"SumPartOfMoney: {results['sumPartOfMoney']:.2f}")

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        run_cli(sys.argv[1].upper(), sys.argv[2])
    else:
        port = int(os.environ.get("PORT", "5000"))
        app.run(host="0.0.0.0", port=port, debug=False)

