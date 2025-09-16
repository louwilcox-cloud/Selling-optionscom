#!/usr/bin/env python3
"""Debug script to test forecast calculation matches calculator exactly"""

import json
import requests
from services.polygon_service import get_options_chain, get_stock_quote

def is_finite_num(x):
    return isinstance(x, (int, float)) and not (x != x or x == float('inf') or x == float('-inf'))

class WeightedMeanResult:
    def __init__(self, value, total_weight):
        self.value = value
        self.total_weight = total_weight

def weighted_mean(rows, value_fn, weight_fn):
    """EXACT copy of calculator.js weightedMean function"""
    total_w = 0
    acc = 0
    for r in rows:
        v = value_fn(r)
        w = weight_fn(r)
        if not is_finite_num(v) or not is_finite_num(w) or w <= 0:
            continue
        acc += v * w
        total_w += w
    value = acc / total_w if total_w > 0 else float('nan')
    return WeightedMeanResult(value, total_w)

def debug_amd_calculation():
    print("=== Debugging AMD 2025-10-10 Calculation ===")
    
    # Test same API calls
    symbol = "AMD"
    date = "2025-10-10"
    
    # Get stock quote
    try:
        quote = get_stock_quote(symbol)
        current_price = float(quote["price"])
        print(f"Current Price: ${current_price}")
    except Exception as e:
        print(f"Error getting quote: {e}")
        return
        
    # Get options chain
    try:
        chain_data = get_options_chain(symbol, date)
        calls = chain_data.get('calls', [])
        puts = chain_data.get('puts', [])
        print(f"Options data: {len(calls)} calls, {len(puts)} puts")
    except Exception as e:
        print(f"Error getting chain: {e}")
        return
    
    # Debug first few options
    print(f"\nFirst 3 calls:")
    for i, call in enumerate(calls[:3]):
        print(f"  Call {i}: strike={call.get('strike')}, lastPrice={call.get('lastPrice')}, volume={call.get('volume')}")
        
    print(f"\nFirst 3 puts:")  
    for i, put in enumerate(puts[:3]):
        print(f"  Put {i}: strike={put.get('strike')}, lastPrice={put.get('lastPrice')}, volume={put.get('volume')}")
    
    # Filter valid options (non-zero prices)
    valid_calls = [c for c in calls if c.get('lastPrice', 0) > 0]
    valid_puts = [p for p in puts if p.get('lastPrice', 0) > 0]
    print(f"\nValid options: {len(valid_calls)} calls, {len(valid_puts)} puts with non-zero prices")
    
    # EXACT same breakeven functions as calculator.js  
    def be_call(r):
        return r.get('strike', 0) + r.get('lastPrice', 0)
    
    def be_put(r):
        return r.get('strike', 0) - r.get('lastPrice', 0)
    
    # EXACT same weight functions as calculator.js
    def weight_vol(r):
        return r.get('lastPrice', 0) * r.get('volume', 0)
    
    def weight_oi(r):
        return r.get('lastPrice', 0) * r.get('openInterest', 0)
    
    # EXACT same calculation as calculator.js
    bulls_vol = weighted_mean(valid_calls, be_call, weight_vol)
    bears_vol = weighted_mean(valid_puts, be_put, weight_vol)
    bulls_oi = weighted_mean(valid_calls, be_call, weight_oi)
    bears_oi = weighted_mean(valid_puts, be_put, weight_oi)
    
    print(f"\nWeighted Mean Results:")
    print(f"Bulls Volume: value={bulls_vol.value:.2f}, weight={bulls_vol.total_weight:.2f}")
    print(f"Bears Volume: value={bears_vol.value:.2f}, weight={bears_vol.total_weight:.2f}")
    print(f"Bulls OI: value={bulls_oi.value:.2f}, weight={bulls_oi.total_weight:.2f}")
    print(f"Bears OI: value={bears_oi.value:.2f}, weight={bears_oi.total_weight:.2f}")
    
    # EXACT same fallback logic as calculator.js (access .value property)
    bulls_want = bulls_vol.value if is_finite_num(bulls_vol.value) else bulls_oi.value
    bears_want = bears_vol.value if is_finite_num(bears_vol.value) else bears_oi.value
    
    # Handle case where both are None (fallback to current price)
    if not is_finite_num(bulls_want):
        bulls_want = current_price
    if not is_finite_num(bears_want):
        bears_want = current_price
    
    # EXACT same consensus calculation as calculator.js
    if is_finite_num(bulls_want) and is_finite_num(bears_want):
        avg_consensus = (bulls_want + bears_want) / 2
    else:
        avg_consensus = current_price
        
    print(f"\n=== FINAL RESULTS ===")
    print(f"Bulls Want: ${bulls_want:.2f}")
    print(f"Bears Want: ${bears_want:.2f}")
    print(f"Avg Consensus: ${avg_consensus:.2f}")
    
    print(f"\n=== EXPECTED FROM CALCULATOR ===")
    print(f"Bulls Want: $170.03")
    print(f"Bears Want: $151.22")
    print(f"Avg Consensus: $160.62")
    
    print(f"\n=== MATCH STATUS ===")
    print(f"Bulls Match: {abs(bulls_want - 170.03) < 0.01}")
    print(f"Bears Match: {abs(bears_want - 151.22) < 0.01}")
    print(f"Consensus Match: {abs(avg_consensus - 160.62) < 0.01}")

if __name__ == "__main__":
    debug_amd_calculation()