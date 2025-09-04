#!/usr/bin/env python3
"""
Simple Flask API for the Options Sentiment Analyzer
Provides endpoints that match your existing API structure
"""

import os
from flask import Flask, request, jsonify, send_from_directory
import yfinance as yf
import pandas as pd
import math

app = Flask(__name__)

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
    """
    all_rows = []
    for src, type_label in [(calls, "Call"), (puts, "Put")]:
        for r in src:
            strike = _safe_float(r.get("strike", 0))
            last_price = _safe_float(r.get("lastPrice", 0))
            oi = int(_safe_float(r.get("openInterest", 0)))
            volume = int(_safe_float(r.get("volume", 0)))

            if type_label == "Call":
                breakeven = strike + last_price
            else:
                breakeven = strike - last_price

            tot_pre = last_price * oi

            all_rows.append({
                "Symbol": symbol,
                "Strike": strike,
                "Exp Date": exp_date,
                "AvgLast": last_price,
                "BreakEven": breakeven,
                "CountOfSymbol": 1,
                "OI": oi,
                "Volume": volume,
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

# API Routes
@app.route("/api/quote")
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

@app.route("/api/get_options_data")
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

@app.route("/api/results_both")
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

# Static file serving
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/calculator.html')
def serve_calculator():
    return send_from_directory('.', 'calculator.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)