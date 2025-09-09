# Fix My Quote — API Surface & Polygon Endpoints

This document lists the app’s REST endpoints, request/response shapes, and the underlying **Polygon** endpoints/fields we rely on. Use this as a contract for future features.

---

## App REST Endpoints

### 1) Health
**GET** `/api/health`  
**200**:
```json
{
  "status":"healthy",
  "timestamp":"2025-09-09T10:22:08-04:00",
  "polygon_api":"configured",
  "market_phase":"open|closed",
  "uptime":"running"
}
```

---

### 2) Quote (stocks/ETFs)
**GET** `/api/quote?symbol=SPY`  
**200**:
```json
{
  "symbol":"SPY",
  "mode":"live" | "eod",
  "price": 501.35,
  "source":"polygon-snapshot:lastTrade | polygon-snapshot:midQuote | polygon-snapshot:day.c | polygon-prev",
  "at":"2025-09-09T09:58:49-04:00"
}
```

**Market behavior**
- `live`: delayed snapshot trades preferred; mid-quote/open/prev as fallbacks; final fallback = previous day bar.
- `eod`: previous day bar preferred; snapshot as fallback.

**Polygon calls**
- `/v2/snapshot/locale/us/markets/stocks/tickers/{SYMBOL}`
- `/v2/aggs/ticker/{SYMBOL}/prev?adjusted=true`

**Fields used**
- `ticker.lastTrade.p`
- `ticker.lastQuote.bp` / `ticker.lastQuote.ap`
- `ticker.day.c`, `ticker.day.o`
- `ticker.prevDay.c`

---

### 3) Market Pulse tiles
**GET** `/api/market-data`  
Returns an array like:
```json
[
  {"name":"S&P 500","price":  x.xxx,"change": y.yyyy,"change_pct": z.zz},
  ...
]
```

**Behavior**
- `live`: price from `/api/quote`; change vs **yesterday close**.
- `eod`: price = **yesterday close**; change `0`.

**Symbols**: `SPY, QQQ, DIA, IWM, TLT, UUP, USO, GLD`

**Polygon calls**
- `/v2/aggs/ticker/{SYMBOL}/prev?adjusted=true` (baseline close)
- plus whatever `/api/quote` used

---

### 4) Options expirations
**GET** `/api/get_options_data?symbol=SPY`  
(when `date` param is omitted)

**200**:
```json
{
  "symbol":"SPY",
  "expirations":["2025-09-09","2025-09-12","..."],
  "count": N,
  "source":"polygon-v3-contracts"
}
```

**Polygon calls (paged)**
- `/v3/reference/options/contracts?underlying_ticker=SPY&expired=false&sort=expiration_date&order=asc&limit=1000`
- Follow `next_url` until exhausted.

**Notes**
- We collect unique `expiration_date` across pages to avoid duplicates.

---

### 5) Options chain (LIVE/EOD)
**GET** `/api/get_options_data?symbol=SPY&date=YYYY-MM-DD` — **LIVE rules**  
**GET** `/api/get_options_data_eod?symbol=SPY&date=YYYY-MM-DD` — **forced EOD**

**200**:
```json
{
  "symbol":"SPY",
  "expiration":"2025-09-09",
  "calls":[{"ticker":"O:SPY...C...","strike":500,"lastPrice":1.23,"volume":1234,"openInterest":4567}],
  "puts":[...],
  "metadata":{
    "source":"polygon-v3-snapshot-chain[+prev-fill]",
    "pages":N,
    "prev_fill_applied":{"calls":X,"puts":Y},
    "mode":"live | eod | eod-forced"
  }
}
```

**LIVE behavior**
- Source: **Options Chain Snapshot** (paged).
- Mapping:
  - `lastPrice`  ← `results[].last_trade.price`
  - `volume`     ← `results[].day.volume`
  - `openInterest` ← `results[].open_interest`
- **No backfill** of zeros.

**EOD / forced EOD**
- Snapshot mapping above **plus backfill** of zeros via per-contract **previous day bar**:
  - `/v2/aggs/ticker/O:{CONTRACT}/prev?adjusted=true` (`c` → `lastPrice`; `v` → `volume` when present)
- If snapshot unavailable:
  - List contracts via `/v3/reference/options/contracts` and use per-contract `/prev` for price/volume (OI unavailable → `0`).

**Polygon calls**
- `/v3/snapshot/options/{UNDERLYING}?expiration_date=YYYY-MM-DD&order=asc&sort=strike_price&limit=250` (paged)
- `/v3/reference/options/contracts?underlying_ticker=...` (fallback listing)
- `/v2/aggs/ticker/O:{CONTRACT}/prev?adjusted=true` (per-contract EOD)

**Fields (snapshot)**
- `results[].details` → `ticker`, `strike_price`, `contract_type`
- `results[].last_trade.price`
- `results[].day.volume`
- `results[].open_interest`

---

### 6) Calculator results (volume/OI models)
**GET** `/api/results_both?symbol=SPY&date=YYYY-MM-DD`

**200** (abridged):
```json
{
  "symbol":"SPY",
  "expiration":"2025-09-09",
  "currentPrice":  x.xx,
  "volume": {
    "prediction": 649.54,
    "pctChange":  1.23,
    "weightSum":  123456.78,
    "contributingRows": 167
  },
  "openInterest": {...},
  "average": {...},
  "debug": {
    "totalOptionsProcessed": 190,
    "volumeWeightSum": ...,
    "oiWeightSum": ...
  }
}
```

**Calculation rules**
- Include a contract only if `lastPrice > 0`.
- Volume model also requires `volume > 0`; OI model requires `openInterest > 0`.
- We compute put/call breakeven-weighted averages and average the two.
- `% change` is vs the stock price returned by `/api/quote`.

---

## Polygon Endpoints Recap (by feature)

**Stocks**
- `GET /v2/snapshot/locale/us/markets/stocks/tickers/{SYMBOL}`  
  Use: `lastTrade.p`, `lastQuote.bp/ap`, `day.c/o`, `prevDay.c`
- `GET /v2/aggs/ticker/{SYMBOL}/prev?adjusted=true`  
  Use: `results[0].c` (previous close)

**Options**
- `GET /v3/reference/options/contracts?...`  
  Use: `results[].expiration_date`, `ticker`, `strike_price`, `contract_type` (paged via `next_url`)
- `GET /v3/snapshot/options/{UNDERLYING}?expiration_date=...`  
  Use: `results[].last_trade.price`, `results[].day.volume`, `results[].open_interest` (paged via `next_url`)
- `GET /v2/aggs/ticker/O:{CONTRACT}/prev?adjusted=true`  
  Use: `results[0].c` (prev close), `results[0].v` (prev volume)

---

## Notes on Entitlements & Delay

- Snapshot returns fields according to your datasets (Trades, Quotes) and delay tier (e.g., 15-minute).  
- Our LIVE options mapping uses **`last_trade.price`**; if a contract hasn’t traded today, it remains `0.0` and is excluded (by design).  
- EOD mode explicitly fills zeros from the previous day.
