# Options Calculator - End of Day Data Implementation Guide

## OBJECTIVE
Get reliable end-of-day (EOD) options data from Polygon.io API to power our Options Sentiment Analyzer calculator that implements Bulls Want/Bears Want predictions using volume and open interest weighting.

## KEY FILES TO ANALYZE

### 1. services/polygon_service.py
**Purpose**: Main Polygon API integration
**Current Issues**: 
- Real-time snapshot API often returns zero volume/open interest
- Many contracts missing market data (bid/ask/last price)
- Rate limiting on individual contract calls

### 2. routes/api.py  
**Purpose**: Flask API endpoints that serve calculator
**Key Endpoints**:
- `/api/get_options_data` - Fetches options expirations
- `/api/results_both` - Returns Bulls Want/Bears Want predictions
- `/api/quote` - Gets stock quotes

### 3. static/calculator.js
**Purpose**: Frontend calculator logic
**Data Requirements**: Needs complete options chains with volume, open interest, strike prices, premiums

### 4. templates/calculator.html
**Purpose**: Calculator user interface
**User Flow**: Symbol → Expiration Date → Analysis Results

### 5. replit.md
**Purpose**: Project architecture overview and mathematical specifications

## CURRENT IMPLEMENTATION PROBLEMS

### Problem 1: Incomplete Market Data
**Issue**: Using `/v3/snapshot/options/{symbol}` API endpoint
**Result**: Many contracts return zero volume, zero open interest, missing prices
**Impact**: Calculator can't perform accurate sentiment analysis

### Problem 2: Real-time vs EOD Data Confusion  
**Issue**: Current implementation tries to get real-time snapshot data
**Need**: End-of-day data would be more complete and reliable for analysis
**Benefit**: EOD data typically has complete volume/OI statistics

### Problem 3: Data Structure Mismatch
**Issue**: Polygon response structure doesn't always match our parsing logic
**Symptoms**: 
```
volume = day.get("volume", 0)  # Often returns 0
open_interest = contract.get("open_interest", 0)  # Often returns 0
```

### Problem 4: Rate Limiting on Contract Fetching
**Issue**: Previous attempts to fetch individual contract market data hit rate limits
**Current Workaround**: Using chain snapshot but data incomplete

## MATHEMATICAL REQUIREMENTS

Our calculator implements this exact algorithm:
```
For Calls: Breakeven = Strike + Premium  
For Puts: Breakeven = Strike - Premium

Volume Weight = Premium × Volume
OI Weight = Premium × Open Interest

P_volume = Σ(Breakeven × Volume_Weight) / Σ(Volume_Weight)
P_oi = Σ(Breakeven × OI_Weight) / Σ(OI_Weight)  
P_average = (P_volume + P_oi) / 2

Bulls Want = P_volume for calls, Bears Want = P_volume for puts
```

**Data Dependencies**: Strike, Premium (last/close price), Volume, Open Interest

## POLYGON API CREDENTIALS
- Account: Upgraded plan with better rate limits
- API Key: Available in environment variables
- Current Endpoints Used:
  - `/v3/reference/options/contracts` - Get contract list
  - `/v3/snapshot/options/{symbol}` - Get market data (problematic)

## DESIRED SOLUTION

**Goal**: Switch to reliable end-of-day options data from Polygon
**Requirements**:
1. Complete volume and open interest data for all active contracts
2. Reliable last/close prices for premium calculations  
3. Full options chain for specified expiration dates
4. Avoid rate limiting issues

**Expected Benefits**:
- More reliable sentiment analysis
- Complete market data coverage
- Better user experience with accurate predictions

## POLYGON EOD OPTIONS ENDPOINTS TO INVESTIGATE

Research these Polygon endpoints for EOD data:
- `/v2/aggs/ticker/{optionsTicker}/range/1/day/{from}/{to}` - Historical aggregates
- `/v3/reference/options/contracts` with different parameters
- Any bulk EOD options data endpoints
- Previous day close data endpoints

## SUCCESS CRITERIA

1. **Complete Data**: All active options contracts have volume, OI, and price data
2. **Reliable API**: No missing data or zero values for actively traded options
3. **Rate Limit Friendly**: Single API call per symbol/expiration combination
4. **Data Quality**: EOD data with final settlement prices and volumes

## TEST CASES

Successful implementation should handle:
- NVDA 2025-09-26 expiration (popular stock with active options)
- AAPL 2025-10-18 expiration (liquid options market)
- Return 50+ contracts with non-zero volume/OI data

Current results show mostly zero volume/OI which breaks the mathematical model.