# Fix My Quote — Architecture & Behavior

This document explains **how the app works**, the **market awareness model**, data flows, and the core design choices so future work builds on solid ground.

---

## Overview

- **Goal:** show reliable stock & options data with rules that match trading reality.
- **Principle:** *The market is either open or it isn’t.* During market hours we show **live (delayed)** trades only; when closed we show **previous session’s close (EOD)**. No fabricated numbers.

---

## Key Components

```
services/
  market_clock.py          # shared market phase (live vs eod) in US/Eastern
  polygon_service.py       # integration with Polygon for stocks & options
routes/
  api.py                   # REST endpoints consumed by the frontend
templates/
  index.html               # Market Pulse grid (4 tiles/row, centered)
```

**Env:** `POLYGON_API_KEY` (required)  
**Libs:** stdlib + `requests`

---

## Market Awareness

- We target **regular US session**: **09:30–16:00 America/New_York**, Monday–Friday, excluding market holidays.
- `market_mode()` returns:
  - `live` — regular session open
  - `eod`  — otherwise (pre, after, weekends/holidays)
- Every feature branches on this:
  - **live:** use **snapshot intraday** data; **do not backfill** options prices.
  - **eod:** use **previous session’s close**; allow **EOD backfill** for options zeros.

This ensures deterministic behavior, no “wishy-washy” pre/post rules.

---

## Stocks: Data Flow

1) **When `live`**
   - Source: **Stocks Snapshot**
   - Price selection order:
     1. `lastTrade.p`
     2. mid-quote `(lastQuote.bp + lastQuote.ap)/2`
     3. `day.c` then `day.o`
     4. `prevDay.c`
   - If snapshot yields nothing valid, fall back to **previous day bar**.

2) **When `eod`**
   - Source: **Previous day bar** first.
   - Snapshot is secondary fallback if needed.

> **Why:** Gives real trade-based price intraday, with sensible fallbacks that never fabricate values.

---

## Options: Data Flow

### Expiration List
- Source: **Reference Contracts** (paged)
- We follow `next_url` to collect **all** expirations; return unique sorted list.

### Chain (per expiration)

**LIVE (market open)**
- Source: **Options Chain Snapshot** (paged)
- Mapping (trades only):
  - `lastPrice` ← `last_trade.price`
  - `volume`    ← `day.volume`   (intraday running)
  - `openInterest` ← `open_interest`
- **No backfills**. Contracts with no trade today remain `0.0` and are **excluded** from calculations.

**EOD (market closed) & Forced EOD**
- Start with snapshot mapping above.
- **Backfill zeros** using per-contract **previous day bar** `/v2/aggs/.../prev` (`c` as lastPrice, optional `v` to replace volume).
- If snapshot unavailable: list contracts (v3), then per-contract `/prev` (OI not available in this fallback → `0`).

---

## Calculator Logic (results_both)

- Pull chain via **LIVE** rules when open, **EOD** when closed.
- **Filters:**
  - Only include rows with `lastPrice > 0`.
  - Volume model: also require `volume > 0`.
  - OI model: also require `openInterest > 0`.
- **Breakeven:**
  - Call: `strike + lastPrice`
  - Put:  `strike − lastPrice`
- **Weights:**
  - Volume model: `weight = lastPrice × volume`
  - OI model:     `weight = lastPrice × openInterest`
- Compute weighted average for calls and puts separately, then average the two.  
- We also show `% change` vs current stock price from `/api/quote`.

> If there aren’t enough live trades (e.g., early in session or illiquid names), tiles return `--` by design.

---

## Market Pulse UI

- API: `/api/market-data` (uses `get_stock_quote()` + previous close for change calc)
- Tiles shown: `SPY, QQQ, DIA, IWM, TLT, UUP, USO, GLD`
- **Layout:** `templates/index.html` enforces **exactly 4 tiles per row**, centered (responsive to 2/1 on smaller screens).
- **When live:** price is delayed snapshot; day change computed vs **yesterday close**.
- **When eod:** price is **yesterday close**, change `0.0`.

---

## Error Handling & Fallbacks (Philosophy)

- Never fabricate prices.
- Prefer trades; quotes may be used only for **stocks** as a mid-quote fallback.
- For options:
  - **live:** trades only; zeros are allowed (and excluded).
  - **eod/forced eod:** fill from previous day to stabilize.

---

## Known Gotchas (Resolved)

1. **Options snapshot field names differ from stocks.**  
   Use `last_trade.price`, `day.volume`, `open_interest`. (Not `p`, `bp/ap`, `day.c`.)

2. **Pagination required** for expirations and snapshot chains.  
   Always follow `next_url` to avoid truncated data.

3. **Indices vs ETFs.**  
   `VIX` is an index (`I:VIX`); ETF/ETN proxies (VIXY/VXX) won’t equal index value. We removed VIX tile to avoid confusion.

---

## Configuration & Dependencies

- `POLYGON_API_KEY` must be present in the environment.
- Dependencies: `requests` (install once; Replit often has it).
- Timezone: `America/New_York` (via `zoneinfo`).

---

## Roadmap Hooks (Optional Later)

- Add an optional “staleness guard” for last trades (ignore if older than N minutes).
- Add an optional quote-mid toggle for options in live if last trade is absent (still no EOD during live).
- Add `I:VIX` support via indices endpoints with clear labeling.
