/* ═══════════════════════════════════════════════════════════════
   tradebot.js  —  AarthiAI TradeBot frontend integration
   Connects to FastAPI TradeBot backend at http://127.0.0.1:8002
   Falls back to demo data when backend is offline.
═══════════════════════════════════════════════════════════════ */

const TB_API   = "http://127.0.0.1:8002";   // TradeBot backend
const TB_USER  = "default";

/* ── Mood configuration (mirrors behavioral/mood.py) ─────────── */
const TB_MOODS = {
  focused:    { label: "Supervised",            gate: 75,  mult: 1.0, maxTrades: 5,  autoEntry: false, autoExit: false, color: "#3b82f6" },
  busy:       { label: "Semi-Auto",             gate: 75,  mult: 1.0, maxTrades: 5,  autoEntry: true,  autoExit: false, color: "#8b5cf6" },
  tired:      { label: "Full AutoTrade",        gate: 82,  mult: 1.0, maxTrades: 3,  autoEntry: true,  autoExit: true,  color: "#f59e0b" },
  out:        { label: "Paused",                gate: 999, mult: 0,   maxTrades: 0,  autoEntry: false, autoExit: false, color: "#6b7280" },
  aggressive: { label: "Semi-Auto Aggressive",  gate: 68,  mult: 1.5, maxTrades: 5,  autoEntry: true,  autoExit: false, color: "#ef4444" },
};

/* ── Sector heat demo (fallback when backend offline) ─────────── */
const TB_DEMO_SECTORS = [
  { sector: "Banking",    heat: 72.4 },
  { sector: "IT",         heat: 68.1 },
  { sector: "Auto",       heat: 61.7 },
  { sector: "Pharma",     heat: 59.3 },
  { sector: "Metal",      heat: 55.8 },
  { sector: "FMCG",       heat: 48.2 },
  { sector: "Realty",     heat: 44.6 },
  { sector: "Energy",     heat: 41.0 },
];

/* ── Demo signals (shown when backend offline) ────────────────── */
const TB_DEMO_SIGNALS = [
  {
    ticker:     "HDFCBANK.NS",
    signal:     "LONG",
    trade_type: "intraday",
    entry:      1742.50, stop: 1718.30, target: 1781.60,
    rsi:        61.4,    vsr: 2.8,
    confidence: 79.2,
    shap_reason:"Bullish signal driven by vwap_dev_pct (↑) and RSI_14 (↑).",
    orb_high:   1745.00, orb_low: 1730.00,
  },
  {
    ticker:     "RELIANCE.NS",
    signal:     "LONG",
    trade_type: "intraday",
    entry:      2948.20, stop: 2904.50, target: 3022.50,
    rsi:        57.8,    vsr: 3.1,
    confidence: 76.5,
    shap_reason:"Bullish signal driven by vsr (↑) and bb_squeeze (↑).",
    orb_high:   2955.00, orb_low: 2930.00,
  },
  {
    ticker:     "TCS.NS",
    signal:     "SHORT",
    trade_type: "swing",
    entry:      3912.00, stop: 3971.40, target: 3792.80,
    rsi:        38.2,    vsr: 1.9,
    confidence: 74.1,
    shap_reason:"Bearish swing: RSI_14 (↓) and ema_cross_bull_daily (↓) are primary drivers.",
    orb_high:   3945.00, orb_low: 3895.00,
  },
];

const TB_DEMO_BRIEF = `═══════════════════════════════════════════════════
  AARTHAI TRADEBOT — DAILY SIGNAL BRIEF  [DEMO]
═══════════════════════════════════════════════════

📡 MARKET CONTEXT
  Global  : Dow +0.42% | Nasdaq +0.68% | SGX Nifty +0.31%
            Crude -0.15% | USD/INR 83.54
  FII/DII : FII Net +1,240 Cr | DII Net +870 Cr
  PCR     : 1.248 — Bullish

🔥 TOP SECTOR HEAT SCORES
  Banking                ███████    72.4/100
  IT                     ██████     68.1/100
  Auto                   ██████     61.7/100
  Pharma                 █████      59.3/100

⚡ INTRADAY PICKS  (2 signals)
  ▶ HDFCBANK.NS  [LONG]  Confidence: 79.2/100
    Entry : ₹1,742.50   Stop : ₹1,718.30   Target : ₹1,781.60
    RSI   : 61.4   VSR : 2.8x   RR : 1:1.67   ATR : ₹14.20
    Why   : Bullish signal driven by vwap_dev_pct (↑) and RSI_14 (↑).

  ▶ RELIANCE.NS  [LONG]  Confidence: 76.5/100
    Entry : ₹2,948.20   Stop : ₹2,904.50   Target : ₹3,022.50
    RSI   : 57.8   VSR : 3.1x   RR : 1:1.70   ATR : ₹29.10
    Why   : Bullish signal driven by vsr (↑) and bb_squeeze (↑).

📈 SWING PICKS  (1 signal)
  ▶ TCS.NS
    EMA Structure : 9 EMA < 21 EMA (bearish)
    RS vs Sector  : -1.82%
    Why : Bearish swing: RSI_14 (↓) and ema_cross_bull_daily (↓).

⚙  AUTOTRADE STATUS
  Mode            : Supervised
  Confidence Gate : 75
  Auto Entry      : NO — awaiting your approval

════  [Demo mode — start TradeBot backend to see live data]  ════`;

/* ── State ───────────────────────────────────────────────────── */
let _tbInitialised  = false;
let _tbCurrentMood  = null;
let _tbBackendOnline = false;
let _tbPollTimer    = null;

/* ══════════════════════════════════════════════════════════════
   PUBLIC API (called by index.html + app.js)
══════════════════════════════════════════════════════════════ */

/**
 * Called once by navigateTo('tradebot') the first time the view opens.
 * Subsequent visits just update data.
 */
function tbInit() {
  if (!_tbInitialised) {
    _tbInitialised = true;
    // ── Immediate: populate view with demo data so it never appears blank ──
    tbRenderSectorHeat(TB_DEMO_SECTORS);
    tbRenderMarketContext({
      fii: { fii_net: 1240, dii_net: 870 },
      nifty_pcr: 1.248,
      global_cues: {
        dow_futures:     { change_pct: 0.42 },
        nasdaq_futures:  { change_pct: 0.68 },
        sgx_nifty_proxy: { change_pct: 0.31 },
        crude_oil:       { change_pct: -0.15 },
        usd_inr:         { price: 83.54 },
      },
    });
    tbRenderSignals(TB_DEMO_SIGNALS);
    tbRenderBrief(TB_DEMO_BRIEF);
    tbSetStatus("⚡ Demo mode — click Run Scan for live signals", "#92400e");
    // ── Async: check if backend is live and upgrade seamlessly ─────────────
    tbCheckBackend().then(() => {
      if (_tbBackendOnline) {
        tbLoadLatestSignals();
        tbLoadBrief();
        tbRefreshRiskStatus();
        tbSetStatus("✓ Backend connected — live data loaded", "#16a34a");
      }
    });
  } else {
    // Already init — just refresh risk status
    tbRefreshRiskStatus();
  }
  // Restore persisted mood
  const saved = localStorage.getItem("tb_mood");
  if (saved && TB_MOODS[saved]) tbSetMood(saved, true);
}

/* ══════════════════════════════════════════════════════════════
   MOOD ENGINE
══════════════════════════════════════════════════════════════ */

function tbSetMood(mood, silent = false) {
  _tbCurrentMood = mood;
  localStorage.setItem("tb_mood", mood);

  // Update button active state
  document.querySelectorAll(".tb-mood-btn").forEach(b => b.classList.remove("active"));
  const btn = document.getElementById(`mood-${mood}`);
  if (btn) {
    btn.classList.add("active");
    if (TB_MOODS[mood]) btn.style.borderColor = TB_MOODS[mood].color;
  }

  // Update status line
  const cfg = TB_MOODS[mood];
  const el  = document.getElementById("tb-mode-status");
  if (el && cfg) {
    const autoTxt = cfg.autoEntry
      ? (cfg.autoExit ? "Full auto entry + exit" : "Auto entry, manual exit")
      : "Manual — awaiting your approval";
    el.style.color = cfg.color;
    el.innerHTML   = `
      <strong style="color:${cfg.color}">${cfg.label}</strong>
      &nbsp;·&nbsp; Confidence gate: ${cfg.gate === 999 ? "PAUSED" : cfg.gate}
      &nbsp;·&nbsp; Position size: ${cfg.mult}×
      &nbsp;·&nbsp; Max trades: ${cfg.maxTrades || "—"}
      &nbsp;·&nbsp; ${autoTxt}
    `;
  }

  // POST to backend if online
  if (!silent && _tbBackendOnline) {
    fetch(`${TB_API}/api/mood`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ user_id: TB_USER, mood }),
    }).catch(() => {});
  }

  tbUpdateAutoTradeGate();
}

function tbUpdateAutoTradeGate() {
  const el = document.getElementById("tb-autotrade-gate");
  if (!el) return;
  const cfg = TB_MOODS[_tbCurrentMood];
  if (!cfg) { el.textContent = "—"; return; }

  if (cfg.autoEntry && cfg.autoExit) {
    el.textContent = "FULL AUTO";
    el.style.color = "#ef4444";
  } else if (cfg.autoEntry) {
    el.textContent = "SEMI-AUTO";
    el.style.color = "#f59e0b";
  } else if (cfg.gate === 999) {
    el.textContent = "PAUSED";
    el.style.color = "#6b7280";
  } else {
    el.textContent = "SUPERVISED";
    el.style.color = "#3b82f6";
  }
}

/* ══════════════════════════════════════════════════════════════
   SCAN
══════════════════════════════════════════════════════════════ */

async function tbRunScan() {
  const btn  = document.querySelector(".tb-scan-btn");
  const chip = document.getElementById("tb-status-chip");

  if (btn) { btn.disabled = true; btn.textContent = "Scanning…"; }
  if (chip) { chip.textContent = "⏳ Scanning…"; chip.style.background = "#854d0e"; }

  tbSetStatus("Scanning…", "#854d0e");

  if (_tbBackendOnline) {
    await tbRunLiveScan();
  } else {
    await tbRunDemoScan();
  }

  if (btn) { btn.disabled = false; btn.textContent = "Run Scan"; }
}

async function tbRunLiveScan() {
  try {
    const resp = await fetch(`${TB_API}/api/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: TB_USER, language: "en" }),
    });
    if (!resp.ok) throw new Error("Scan API error");

    // Poll for results (scan runs async)
    await new Promise(r => setTimeout(r, 4000));
    await tbLoadLatestSignals();
    await tbLoadBrief();
    await tbRefreshRiskStatus();
    tbSetStatus("✓ Scan complete", "#16a34a");
  } catch (e) {
    console.warn("Live scan failed, using demo:", e);
    await tbRunDemoScan();
  }
}

async function tbRunDemoScan() {
  // Simulate a 2-second scan delay
  await new Promise(r => setTimeout(r, 2000));
  tbRenderSectorHeat(TB_DEMO_SECTORS);
  tbRenderMarketContext({
    fii: { fii_net: 1240, dii_net: 870 },
    nifty_pcr: 1.248,
    global_cues: {
      dow_futures:     { change_pct: 0.42 },
      nasdaq_futures:  { change_pct: 0.68 },
      sgx_nifty_proxy: { change_pct: 0.31 },
      crude_oil:       { change_pct: -0.15 },
      usd_inr:         { price: 83.54 },
    },
  });
  tbRenderSignals(TB_DEMO_SIGNALS);
  tbRenderBrief(TB_DEMO_BRIEF);
  tbSetStatus("✓ Demo scan complete", "#16a34a");
}

/* ══════════════════════════════════════════════════════════════
   BACKEND POLLING
══════════════════════════════════════════════════════════════ */

async function tbCheckBackend() {
  try {
    const resp = await fetch(`${TB_API}/health`, { signal: AbortSignal.timeout(2000) });
    _tbBackendOnline = resp.ok;
  } catch {
    _tbBackendOnline = false;
  }

  const chip = document.getElementById("tb-status-chip");
  if (_tbBackendOnline) {
    if (chip) { chip.textContent = "✓ Backend connected"; chip.style.background = "#16a34a"; }
  } else {
    if (chip) { chip.textContent = "⚡ Demo mode — backend offline"; chip.style.background = "#92400e"; }
  }
  return _tbBackendOnline;
}

async function tbLoadLatestSignals() {
  try {
    const resp = await fetch(`${TB_API}/api/signals/latest?user_id=${TB_USER}`);
    if (!resp.ok) return;
    const data = await resp.json();
    const picks = data?.top_signals || [];
    if (picks.length) {
      tbRenderSignals(picks.map(p => ({
        ticker:       p.ticker,
        signal:       p.signal,
        trade_type:   "intraday",
        entry:        p.entry,
        stop:         p.stop,
        target:       p.target,
        rsi:          50,
        vsr:          1.0,
        confidence:   p.confidence,
        shap_reason:  p.reason,
      })));
    }
    if (data?.sector_heats?.length) tbRenderSectorHeat(data.sector_heats);
    if (data?.market_context)        tbRenderMarketContext(data.market_context);
  } catch (e) {
    console.warn("Signal load failed:", e);
  }
}

async function tbLoadBrief() {
  try {
    const resp = await fetch(`${TB_API}/api/brief?user_id=${TB_USER}`);
    if (!resp.ok) return;
    const data = await resp.json();
    if (data.brief) tbRenderBrief(data.brief);
  } catch {}
}

async function tbRefreshRiskStatus() {
  const limitEl = document.getElementById("tb-risk-limit");
  const usedEl  = document.getElementById("tb-risk-used");
  const leftEl  = document.getElementById("tb-risk-left");

  if (!_tbBackendOnline) {
    if (limitEl) limitEl.textContent = "₹2,000";
    if (usedEl)  usedEl.textContent  = "₹0";
    if (leftEl)  leftEl.textContent  = "₹2,000";
    return;
  }
  try {
    const resp = await fetch(`${TB_API}/api/risk/status/${TB_USER}`);
    if (!resp.ok) return;
    const d = await resp.json();
    if (limitEl) limitEl.textContent = "₹" + d.daily_limit.toLocaleString("en-IN");
    if (usedEl)  usedEl.textContent  = "₹" + d.risk_used.toLocaleString("en-IN");
    if (leftEl)  leftEl.textContent  = "₹" + d.risk_remaining.toLocaleString("en-IN");
  } catch {}
}

/* ══════════════════════════════════════════════════════════════
   RENDER HELPERS
══════════════════════════════════════════════════════════════ */

function tbRenderSectorHeat(sectors) {
  const el = document.getElementById("tb-sector-list");
  if (!el) return;
  el.innerHTML = sectors.slice(0, 8).map(s => {
    const heat   = typeof s.heat === "number" ? s.heat : 50;
    const color  = heat >= 70 ? "#ef4444" : heat >= 55 ? "#f59e0b" : "#22c55e";
    const bars   = Math.round(heat / 10);
    return `
      <div class="tb-sector-row">
        <span class="tb-sector-name">${s.sector || s.name || "—"}</span>
        <span class="tb-sector-bar">
          ${"█".repeat(bars)}<span style="color:#374151">${"░".repeat(10 - bars)}</span>
        </span>
        <span class="tb-sector-score" style="color:${color}">${heat.toFixed(1)}</span>
      </div>`;
  }).join("");
}

function tbRenderMarketContext(ctx) {
  const el   = document.getElementById("tb-context-list");
  if (!el)   return;
  const fii  = ctx.fii  || {};
  const gcues = ctx.global_cues || {};

  const fmt = (v, prefix = "") => {
    if (v === undefined || v === null || isNaN(v)) return "—";
    const n = typeof v === "object" ? (v.change_pct ?? v.price ?? 0) : v;
    const c = n >= 0 ? "#22c55e" : "#ef4444";
    return `<span style="color:${c}">${prefix}${n >= 0 ? "+" : ""}${typeof n === "number" ? n.toFixed(2) : n}</span>`;
  };

  const pcr      = ctx.nifty_pcr || 1;
  const pcrLabel = pcr >= 1.2 ? "Bullish" : pcr <= 0.8 ? "Bearish" : "Neutral";
  const pcrColor = pcr >= 1.2 ? "#22c55e" : pcr <= 0.8 ? "#ef4444" : "#f59e0b";

  el.innerHTML = `
    <div class="tb-ctx-row"><span>FII Net</span>  <span>${fmt(fii.fii_net || 0)} Cr</span></div>
    <div class="tb-ctx-row"><span>DII Net</span>  <span>${fmt(fii.dii_net || 0)} Cr</span></div>
    <div class="tb-ctx-row"><span>Nifty PCR</span><span style="color:${pcrColor}">${pcr.toFixed(3)} — ${pcrLabel}</span></div>
    <div class="tb-ctx-row"><span>Dow Futures</span>   <span>${fmt(gcues.dow_futures)}%</span></div>
    <div class="tb-ctx-row"><span>Nasdaq Futs</span>   <span>${fmt(gcues.nasdaq_futures)}%</span></div>
    <div class="tb-ctx-row"><span>SGX Nifty</span>     <span>${fmt(gcues.sgx_nifty_proxy)}%</span></div>
    <div class="tb-ctx-row"><span>Crude Oil</span>     <span>${fmt(gcues.crude_oil)}%</span></div>
    <div class="tb-ctx-row"><span>USD/INR</span>
      <span style="color:#a78bfa">${gcues.usd_inr?.price?.toFixed(2) ?? "—"}</span>
    </div>`;
}

function tbRenderSignals(signals) {
  const el = document.getElementById("tb-signals-grid");
  if (!el) return;

  if (!signals || !signals.length) {
    el.innerHTML = `<div class="tb-empty" style="grid-column:1/-1">No signals above confidence threshold today.</div>`;
    return;
  }

  el.innerHTML = signals.map(s => {
    const isLong   = s.signal === "LONG";
    const confCls  = s.confidence >= 82 ? "conf-fire" : s.confidence >= 75 ? "conf-ok" : "";
    const sideColor = isLong ? "#22c55e" : "#ef4444";
    const rr = s.stop && s.entry && s.target
      ? Math.abs(s.target - s.entry) / Math.abs(s.entry - s.stop)
      : 0;

    return `
    <div class="tb-signal-card ${isLong ? "card-long" : "card-short"}">
      <div class="tb-sig-top">
        <span class="tb-sig-ticker">${s.ticker.replace(".NS","").replace(".BO","")}</span>
        <span class="tb-sig-badge" style="background:${sideColor}20;color:${sideColor};border:1px solid ${sideColor}40">${s.signal}</span>
        <span class="tb-sig-conf ${confCls}">${s.confidence.toFixed(1)}</span>
      </div>
      <div class="tb-sig-prices">
        <div class="tb-sig-price-row"><span class="tb-sig-pl">Entry</span><span>₹${s.entry.toLocaleString("en-IN",{maximumFractionDigits:2})}</span></div>
        <div class="tb-sig-price-row"><span class="tb-sig-pl">Stop</span> <span style="color:#ef4444">₹${s.stop.toLocaleString("en-IN",{maximumFractionDigits:2})}</span></div>
        <div class="tb-sig-price-row"><span class="tb-sig-pl">Target</span><span style="color:#22c55e">₹${s.target.toLocaleString("en-IN",{maximumFractionDigits:2})}</span></div>
      </div>
      <div class="tb-sig-meta">
        RSI ${s.rsi?.toFixed(1) ?? "—"} &nbsp;·&nbsp;
        VSR ${s.vsr?.toFixed(2) ?? "—"}× &nbsp;·&nbsp;
        RR 1:${rr.toFixed(2)} &nbsp;·&nbsp;
        <span style="color:#a78bfa;text-transform:capitalize">${s.trade_type || "intraday"}</span>
      </div>
      <div class="tb-sig-why">${s.shap_reason || ""}</div>
      <div class="tb-sig-actions">
        <button class="tb-sig-btn tb-sig-btn-approve"
                onclick="tbApprove(${JSON.stringify(s).replace(/"/g,"'")})"
                ${_tbCurrentMood === "out" ? "disabled" : ""}>
          Approve Trade
        </button>
        <button class="tb-sig-btn tb-sig-btn-skip" onclick="this.closest('.tb-signal-card').style.opacity='0.4'">
          Skip
        </button>
      </div>
    </div>`;
  }).join("");
}

function tbRenderBrief(text) {
  const el = document.getElementById("tb-brief-pre");
  if (el) el.textContent = text;
}

function tbSetStatus(msg, color = "#16a34a") {
  const chip = document.getElementById("tb-status-chip");
  if (chip) { chip.textContent = msg; chip.style.background = color; }
}

/* ══════════════════════════════════════════════════════════════
   APPROVE TRADE — calls TradeBot API or shows toast
══════════════════════════════════════════════════════════════ */

async function tbApprove(signal) {
  if (_tbCurrentMood === "out") {
    tbToast("AutoTrade is paused — change your mood first.", "warn");
    return;
  }
  const cfg = TB_MOODS[_tbCurrentMood || "focused"];

  if (!_tbBackendOnline) {
    tbToast(`[Demo] Would execute ${signal.signal} ${signal.ticker} @ ₹${signal.entry.toFixed(2)}`, "ok");
    return;
  }

  tbToast("Placing trade…", "info");
  try {
    const resp = await fetch(`${TB_API}/api/trade/execute`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        user_id:    TB_USER,
        ticker:     signal.ticker,
        signal:     signal.signal,
        entry:      signal.entry,
        stop:       signal.stop,
        target:     signal.target,
        trade_type: signal.trade_type || "intraday",
      }),
    });
    const result = await resp.json();
    if (result.status === "OK") {
      tbToast(`✅ Trade placed: ${signal.signal} ${signal.ticker} x${result.qty} @ ₹${signal.entry.toFixed(2)}`, "ok");
    } else {
      tbToast(`❌ Blocked: ${result.reason}`, "warn");
    }
  } catch (e) {
    tbToast(`❌ Error: ${e.message}`, "warn");
  }
}

/* ── Toast helper ─────────────────────────────────────────────── */
function tbToast(msg, type = "info") {
  const colors = { ok: "#16a34a", warn: "#dc2626", info: "#2563eb" };
  const t = document.createElement("div");
  t.className = "tb-toast";
  t.textContent = msg;
  t.style.background = colors[type] || "#1f2937";
  document.body.appendChild(t);
  requestAnimationFrame(() => t.classList.add("show"));
  setTimeout(() => { t.classList.remove("show"); setTimeout(() => t.remove(), 400); }, 3500);
}
