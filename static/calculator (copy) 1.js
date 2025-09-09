/* static/calculator.js
   Computes Bulls/Consensus/Bears and fills Volume/OI Put/Call ratios.
   Hardened to handle varied OI keys and numeric strings with commas.
*/
(function () {
  const DEBUG = new URL(window.location.href).searchParams.get('debug') === '1';

  function $(id) { return document.getElementById(id); }
  const els = {
    form: $('calculatorForm'),
    symbol: $('symbol'),
    expiration: $('expiration'),
    loading: $('loadingState'),
    errorBox: $('errorState'),
    errorMsg: $('errorMessage'),
    results: $('resultsSection'),
    priceOut: $('currentPrice'),
    bullsOut: $('bullsValue'),
    bearsOut: $('bearsValue'),
    consOut:  $('consensusValue'),
    volumePCRatio: $('volumePCRatio'),
    oiPCRatio: $('oiPCRatio'),

    // optional debug nodes (may not exist)
    rawExpirations: $('rawExpirations'),
    rawChain: $('rawOptionsChain'),
    pcRatios: $('pcRatiosContent'),
    calcSteps: $('calculationSteps'),
    volCalcs: $('volumeCalcs'),
    oiCalcs: $('oiCalcs'),
    pcRatiosContainer: $('pcRatiosContainer'),
    optionsChainContainer: $('optionsChainContainer'),
    dataDebugContainer: $('dataDebugContainer'),
    calcsContainer: $('calcsContainer'),
  };

  // Hide debug accordions unless ?debug=1
  (function hideDebugBlocksIfNeeded(){
    if (DEBUG) return;
    [
      els.pcRatiosContainer, els.optionsChainContainer,
      els.dataDebugContainer, els.calcsContainer,
      els.rawExpirations, els.rawChain, els.pcRatios,
      els.calcSteps, els.volCalcs, els.oiCalcs
    ].forEach(el => { if (el) el.style.display = 'none'; });
  })();

  function show(el) { el && el.classList.remove('hidden'); }
  function hide(el) { el && el.classList.add('hidden'); }
  function setText(el, v) { if (el) el.textContent = v; }
  function fmt(n, d=2) { return (n == null || Number.isNaN(n)) ? '--' : Number(n).toFixed(d); }
  function toArray(x){ return Array.isArray(x) ? x : (x ? [x] : []); }
  function isFiniteNum(x){ return typeof x === 'number' && Number.isFinite(x); }

  // Parse numbers safely, handling strings like "12,345", "1_234", "  123 "
  function toNum(x){
    if (x == null) return 0;
    if (typeof x === 'number') return Number.isFinite(x) ? x : 0;
    if (typeof x === 'string') {
      const cleaned = x.replace(/[,_\s]/g, '');
      const n = Number(cleaned);
      return Number.isFinite(n) ? n : 0;
    }
    // booleans/others → 0
    const n = Number(x);
    return Number.isFinite(n) ? n : 0;
  }

  async function apiGet(url) {
    const r = await fetch(url, { headers: { 'Accept': 'application/json' }});
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  // ---------- Expirations ----------
  async function loadExpirations(symbol) {
    if (!symbol) return;
    hide(els.errorBox); show(els.loading);
    try {
      const j = await apiGet(`/api/get_options_data?symbol=${encodeURIComponent(symbol)}`);
      const dates = extractDates(j);
      els.expiration.innerHTML = `<option value="">Select expiration</option>` +
        dates.map(d => `<option value="${d}">${d}</option>`).join('');
      if (DEBUG && els.rawExpirations) els.rawExpirations.textContent = JSON.stringify(j, null, 2);
    } catch (e) {
      showError(`Could not load expirations for ${symbol}: ${e.message}`);
    } finally {
      hide(els.loading);
    }
  }

  function extractDates(obj) {
    const out = new Set();
    const rx = /\b20\d{2}-\d{2}-\d{2}\b/;
    (function walk(v){
      if (v == null) return;
      if (typeof v === 'string') { const m = v.match(rx); if (m) out.add(m[0]); return; }
      if (Array.isArray(v)) { v.forEach(walk); return; }
      if (typeof v === 'object') { Object.values(v).forEach(walk); }
    })(obj);
    return Array.from(out).sort();
  }

  // ---------- Underlying quote ----------
  async function loadQuote(symbol) {
    try {
      const jq = await apiGet(`/api/quote?symbol=${encodeURIComponent(symbol)}`);
      const price = jq && (jq.price ?? jq.close ?? jq.last);
      setText(els.priceOut, `$${fmt(price, 2)}`);
    } catch {
      setText(els.priceOut, '--');
    }
  }

  // ---------- Chain + Calculations ----------
  async function loadChainAndCalculate(symbol, date) {
    hide(els.errorBox); show(els.loading);
    try {
      const chain = await apiGet(`/api/get_options_data?symbol=${encodeURIComponent(symbol)}&date=${encodeURIComponent(date)}`);
      if (DEBUG && els.rawChain) els.rawChain.textContent = JSON.stringify(chain, null, 2);

      const calls = normalizeSide(chain.calls || chain.Calls || chain.call || []);
      const puts  = normalizeSide(chain.puts  || chain.Puts  || chain.put  || []);

      if (!calls.length && !puts.length) throw new Error('No chain data returned');

      // Totals for standard P/C ratios (contract counts)
      const vCalls = sum(calls.map(r => r.volume));
      const vPuts  = sum(puts.map(r => r.volume));
      const oiCalls = sum(calls.map(r => r.openInterest));
      const oiPuts  = sum(puts.map(r => r.openInterest));

      const pcrVol = vCalls > 0 ? (vPuts / vCalls) : null;
      const pcrOI  = oiCalls > 0 ? (oiPuts / oiCalls) : null;

      if (els.volumePCRatio) setText(els.volumePCRatio, pcrVol == null ? '--' : fmt(pcrVol, 2));
      if (els.oiPCRatio)     setText(els.oiPCRatio,     pcrOI  == null ? '--' : fmt(pcrOI, 2));

      if (DEBUG && els.pcRatios) {
        els.pcRatios.textContent = JSON.stringify({
          totals: { vCalls, vPuts, oiCalls, oiPuts },
          ratios: { pcrVol, pcrOI }
        }, null, 2);
      }

      // Breakevens
      const beCall = r => r.strike + r.lastPrice;  // strike + premium
      const bePut  = r => r.strike - r.lastPrice;  // strike - premium

      // Weighting for Bulls/Bears: prefer dollar volume; fallback to OI dollars
      const weightVol = r => r.lastPrice * r.volume;
      const weightOI  = r => r.lastPrice * r.openInterest;

      const bullsVol = weightedMean(calls, beCall, weightVol);
      const bearsVol = weightedMean(puts,  bePut,  weightVol);
      const bullsOI  = weightedMean(calls, beCall, weightOI);
      const bearsOI  = weightedMean(puts,  bePut,  weightOI);

      const bulls = isFiniteNum(bullsVol.value) ? bullsVol.value : bullsOI.value;
      const bears = isFiniteNum(bearsVol.value) ? bearsVol.value : bearsOI.value;
      const consensus = (isFiniteNum(bulls) && isFiniteNum(bears)) ? (bulls + bears) / 2 : null;

      setText(els.bullsOut, `$${fmt(bulls, 2)}`);
      setText(els.bearsOut, `$${fmt(bears, 2)}`);
      setText(els.consOut,  `$${fmt(consensus, 2)}`);

      if (DEBUG && els.calcSteps) {
        els.calcSteps.innerHTML = `
          <div><strong>Method:</strong> Dollar-volume weighted breakevens; fallback to OI dollar-weighted if volume is all zero.</div>
          <div><strong>Calls BE:</strong> strike + lastPrice</div>
          <div><strong>Puts BE:</strong> strike - lastPrice</div>
          <div><strong>Weights:</strong> w_vol = lastPrice × volume; w_oi = lastPrice × openInterest</div>
        `;
      }
      if (DEBUG && els.volCalcs) els.volCalcs.textContent = JSON.stringify({calls: bullsVol.steps, puts: bearsVol.steps}, null, 2);
      if (DEBUG && els.oiCalcs)  els.oiCalcs.textContent  = JSON.stringify({calls: bullsOI.steps,  puts: bearsOI.steps }, null, 2);

      show(els.results);
    } catch (e) {
      showError(e.message || String(e));
    } finally {
      hide(els.loading);
    }
  }

  function normalizeSide(sideArr) {
    return toArray(sideArr).map(r => {
      // Accept many possible OI keys and normalize to a number
      const oiRaw =
        r.openInterest ?? r.open_interest ?? r.openInterestEOD ??
        r.open_interest_eod ?? r.oi ?? r.OI ?? r.openInt ?? r.OpenInterest;

      return {
        strike:      toNum(r.strike ?? r.Strike),
        lastPrice:   toNum(r.lastPrice ?? r.Last ?? r.last ?? r.price),
        volume:      toNum(r.volume ?? r.Volume),
        openInterest: toNum(oiRaw),
      };
    }).filter(r => isFiniteNum(r.strike));
  }

  function weightedMean(rows, valueFn, weightFn) {
    let totalW = 0, acc = 0;
    const steps = [];
    for (const r of rows) {
      const v = valueFn(r);
      const w = weightFn(r);
      if (!isFiniteNum(v) || !isFiniteNum(w) || w <= 0) continue;
      steps.push({ value: Number(v.toFixed(6)), weight: Number(w.toFixed(6)), part: Number((v*w).toFixed(6)) });
      acc += v * w; totalW += w;
    }
    return { value: totalW > 0 ? acc / totalW : NaN, steps, totalWeight: totalW };
  }

  function sum(a){ return a.reduce((s,x)=>s+(isFiniteNum(x)?x:0),0); }

  function showError(msg){
    if (els.errorMsg) setText(els.errorMsg, msg || 'Error');
    show(els.errorBox); hide(els.results);
  }

  // ---------- Wiring ----------
  if (els.symbol) {
    els.symbol.addEventListener('change', () => {
      const s = (els.symbol.value || '').trim().toUpperCase();
      if (s) loadExpirations(s);
    });
  }
  if (els.form) {
    els.form.addEventListener('submit', (e) => {
      e.preventDefault();
      const symbol = (els.symbol.value || '').trim().toUpperCase();
      const date = (els.expiration.value || '').trim();
      if (!symbol) return showError('Enter a stock symbol.');
      if (!date)   return showError('Choose an expiration date.');
      loadQuote(symbol);
      loadChainAndCalculate(symbol, date);
    });
  }

  // Optional: prefill from URL (?symbol=...&date=...)
  (function initFromQuery(){
    const u = new URL(window.location.href);
    const s = (u.searchParams.get('symbol') || '').toUpperCase();
    const d = u.searchParams.get('date') || '';
    if (s) { els.symbol.value = s; loadExpirations(s).then(()=>{ if (d) els.expiration.value = d; }); }
  })();
})();
