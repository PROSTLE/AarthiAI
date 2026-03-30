// ============================================================================
// SPA NAVIGATION
// ============================================================================

const API = "http://127.0.0.1:8000";

const VIEWS = ["markets", "funds", "sip", "company", "orders"];

function navigateTo(view) {
  // Hide all views
  VIEWS.forEach(v => {
    const el = document.getElementById(`view-${v}`);
    if (el) el.classList.add("hidden");
  });

  // Show target
  const target = document.getElementById(`view-${view}`);
  if (target) target.classList.remove("hidden");

  // Update nav active states (topnav + sidenav)
  VIEWS.forEach(v => {
    const tn = document.getElementById(`nav-${v}`);
    const sn = document.getElementById(`snav-${v}`);
    const isActive = v === view;
    if (tn) tn.classList.toggle("active", isActive);
    if (sn) sn.classList.toggle("active", isActive);
  });

  // Toggle contextual search bars
  const marketsSearch = document.getElementById("marketsSearch");
  const analyzeBtn    = document.getElementById("analyzeBtn");
  const fundsSearch   = document.getElementById("fundsSearch");
  const companySearch = document.getElementById("companySearch");
  const companyAnalyzeBtn = document.getElementById("companyAnalyzeBtn");

  [marketsSearch, analyzeBtn, fundsSearch, companySearch, companyAnalyzeBtn].forEach(el => el && el.classList.add("hidden"));

  if (view === "markets") {
    marketsSearch && marketsSearch.classList.remove("hidden");
    analyzeBtn    && analyzeBtn.classList.remove("hidden");
  } else if (view === "funds") {
    fundsSearch && fundsSearch.classList.remove("hidden");
    if (!_fundsLoaded) { loadFunds(); loadTopFunds(); _fundsLoaded = true; }
  } else if (view === "company") {
    companySearch && companySearch.classList.remove("hidden");
    companyAnalyzeBtn && companyAnalyzeBtn.classList.remove("hidden");
  } else if (view === "orders") {
    // orders view uses existing trading view logic — init account chart
    if (window.initAccountChart) initAccountChart();
  }

  // Push state for back button support
  history.pushState({ view }, "", `#${view}`);
}

// Back button support
window.addEventListener("popstate", e => {
  if (e.state && e.state.view) navigateTo(e.state.view);
});

// Helper: load a ticker directly from the markets view empty state hints
function loadTickerDirect(ticker) {
  navigateTo("markets");
  document.getElementById("tickerInput").value = ticker;
  loadTicker();
}

// ============================================================================
// MUTUAL FUNDS MODULE
// ============================================================================

let _fundsLoaded = false;
let allFunds = [];
let scatterChart = null;

async function loadFunds() {
  try {
    const res = await fetch(`${API}/api/mutual-funds`);
    const data = await res.json();
    allFunds = data.funds;
    renderFundList(allFunds);
    renderScatterChart(allFunds);
  } catch (e) {
    const el = document.getElementById("fundList");
    if (el) el.innerHTML = `<div class="mf-loading" style="color:var(--on-tertiary-cont)">⚠ Backend offline — start the FastAPI server</div>`;
  }
}

async function loadTopFunds() {
  try {
    const res = await fetch(`${API}/api/mutual-funds/top`);
    const data = await res.json();
    renderAlphaList(data.top_alpha, "topAlphaList");
    renderAlphaList(data.top_stable, "topStableList");
    const aiEl = document.getElementById("aiSignalText");
    if (aiEl) aiEl.textContent = data.ai_signal;
    renderAmcTable(allFunds);
  } catch (e) {}
}

function renderFundList(funds) {
  const el = document.getElementById("fundList");
  if (!el) return;
  if (!funds.length) { el.innerHTML = `<div class="mf-loading">No funds found in this category.</div>`; return; }
  el.innerHTML = funds.map(f => {
    const catClass = { Equity: "badge-eq", Debt: "badge-debt", Hybrid: "badge-hybrid", Index: "badge-index" }[f.category] || "badge-eq";
    const riskClass = { Low: "badge-risk-low", Moderate: "badge-risk-mod", High: "badge-risk-high", "Very High": "badge-risk-vh" }[f.risk] || "badge-risk-mod";
    const stars = "★".repeat(f.rating) + "☆".repeat(5 - f.rating);
    const initial = f.amc[0];
    return `
      <div class="fund-card" onclick="openSipForFund('${f.name}')">
        <div class="fund-avatar">${initial}</div>
        <div class="fund-info">
          <h4>${f.name}</h4>
          <div class="fund-meta">
            <span class="fund-badge ${catClass}">${f.sub_category}</span>
            <span class="fund-badge ${riskClass}">${f.risk}</span>
            <span class="badge-stars">${stars}</span>
          </div>
        </div>
        <div class="fund-stats">
          <div class="fs-row"><span class="fs-label">NAV</span><span class="fs-val">₹${f.nav.toFixed(2)}</span></div>
          <div class="fs-row"><span class="fs-label">AUM</span><span class="fs-val">₹${(f.aum_cr/100).toFixed(0)}B</span></div>
          <div class="fs-row"><span class="fs-label">Exp.</span><span class="fs-val">${f.expense_ratio}%</span></div>
        </div>
        <div class="fund-returns">
          <div class="fr-value">+${f.return_1y}%</div>
          <div class="fr-label">1Y Return</div>
          <div style="font-size:11px;color:var(--outline);margin-top:4px">3Y: +${f.return_3y}% · 5Y: +${f.return_5y}%</div>
        </div>
        <div class="fund-action">
          <button class="btn-invest" onclick="event.stopPropagation();openSipForFund('${f.name}')">Start SIP</button>
          <div class="min-sip">Min ₹${f.min_sip}/mo</div>
        </div>
      </div>
    `;
  }).join("");
}

function renderAlphaList(funds, containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = funds.map(f => `
    <div class="alpha-item">
      <div>
        <div class="alpha-name">${f.name}</div>
        <div class="alpha-sub">${f.amc} · ${f.sub_category}</div>
      </div>
      <div class="alpha-return">+${f.return_1y}%</div>
    </div>
  `).join("");
}

function renderAmcTable(funds) {
  const el = document.getElementById("amcTableBody");
  if (!el || !funds.length) return;
  const amcs = {};
  funds.forEach(f => {
    if (!amcs[f.amc]) amcs[f.amc] = { returns: [], expense: [] };
    amcs[f.amc].returns.push(f.return_3y);
    amcs[f.amc].expense.push(f.expense_ratio);
  });
  const rows = Object.entries(amcs).map(([amc, d]) => {
    const avgReturn = (d.returns.reduce((a,b)=>a+b,0)/d.returns.length).toFixed(1);
    const avgExp = (d.expense.reduce((a,b)=>a+b,0)/d.expense.length).toFixed(2);
    const conf = Math.min(95, Math.round(50 + avgReturn * 1.8));
    const risk = avgReturn > 20 ? "Aggressive" : avgReturn > 14 ? "Moderate" : "Conservative";
    const riskColor = avgReturn > 20 ? "var(--on-tertiary-cont)" : avgReturn > 14 ? "#eab308" : "var(--secondary)";
    return `<tr>
      <td class="amc-name">${amc} Mutual Fund</td>
      <td class="amc-return">+${avgReturn}%</td>
      <td style="color:var(--on-surf-var)">${avgExp}%</td>
      <td><span style="padding:2px 8px;border-radius:3px;background:rgba(255,255,255,0.05);color:${riskColor};font-size:11px;font-weight:700">${risk}</span></td>
      <td><div class="conf-bar-wrap"><div class="conf-bar-fill" style="width:${conf}%"></div></div></td>
    </tr>`;
  });
  el.innerHTML = rows.join("");
}

function renderScatterChart(funds) {
  const canvas = document.getElementById("scatterChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (scatterChart) scatterChart.destroy();
  scatterChart = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [{
        label: "Funds",
        data: funds.map(f => ({ x: f.expense_ratio, y: f.return_3y, label: f.name })),
        backgroundColor: funds.map(f => f.return_3y > 25 ? "rgba(64,229,108,0.7)" : f.return_3y > 15 ? "rgba(168,232,255,0.7)" : "rgba(133,147,152,0.5)"),
        borderColor: "transparent",
        pointRadius: funds.map(f => Math.max(6, Math.min(18, f.aum_cr / 5000))),
        pointHoverRadius: funds.map(f => Math.max(8, Math.min(22, f.aum_cr / 5000))),
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: "#1a1c20", borderColor: "rgba(60,73,78,0.3)", borderWidth: 1,
          callbacks: { label: c => [`${c.raw.label}`, `Expense: ${c.raw.x}%`, `3Y Return: +${c.raw.y}%`] } }
      },
      scales: {
        x: { title: { display: true, text: "Expense Ratio (%)", color: "#859398", font: { size: 10 } }, grid: { color: "rgba(60,73,78,0.1)" }, ticks: { color: "#859398" } },
        y: { title: { display: true, text: "3Y Annualized Return (%)", color: "#859398", font: { size: 10 } }, grid: { color: "rgba(60,73,78,0.1)" }, ticks: { color: "#859398" } }
      }
    }
  });
}

function filterFunds(cat, btn) {
  document.querySelectorAll(".cat-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  const filtered = cat === "all" ? allFunds : allFunds.filter(f => f.category === cat);
  renderFundList(filtered);
  renderScatterChart(filtered);
}

function openSipForFund(name) {
  navigateTo("sip");
  document.getElementById("fundCat").value = "12";
  applySipPreset("12");
}

function switchMfTab(tab, btn) {
  const explorer = document.getElementById("mfExplorerTab");
  const brief    = document.getElementById("mfBriefTab");
  // Deactivate all cat-btn active states
  document.querySelectorAll(".cat-filters .cat-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");

  if (tab === "brief") {
    if (explorer) explorer.classList.add("hidden");
    if (brief)    brief.classList.remove("hidden");
    // Auto-load if not yet loaded
    if (!_briefLoaded) loadFundBrief();
  } else {
    if (brief)    brief.classList.add("hidden");
    if (explorer) explorer.classList.remove("hidden");
    // Re-activate "All Funds" button
    const allBtn = document.querySelector('.cat-btn[data-cat="all"]');
    if (allBtn) allBtn.classList.add("active");
  }
}

// MF search filter (wired to mfSearch in topnav)
document.addEventListener("DOMContentLoaded", () => {
  const mfSearchEl = document.getElementById("mfSearch");
  if (mfSearchEl) {
    mfSearchEl.addEventListener("input", e => {
      const q = e.target.value.toLowerCase();
      if (!q) { renderFundList(allFunds); return; }
      renderFundList(allFunds.filter(f =>
        f.name.toLowerCase().includes(q) || f.amc.toLowerCase().includes(q) || f.sub_category.toLowerCase().includes(q)
      ));
    });
  }
});

// ============================================================================
// SIP CALCULATOR MODULE
// ============================================================================

let projChart = null;

function syncSipInput(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
  const displayMap = { sipAmt: "sipAmtDisplay", sipYrs: "sipYrsDisplay", sipRet: "sipRetDisplay", stepUp: "stepUpDisplay" };
  const dispEl = document.getElementById(displayMap[id]);
  if (dispEl) {
    dispEl.textContent = id === "sipAmt" ? "₹" + Number(val).toLocaleString("en-IN") : val + (id === "sipYrs" ? " Years" : "%");
  }
}
function syncSipSlider(sliderId, val) {
  const el = document.getElementById(sliderId);
  if (el) el.value = val;
}
function updateSipDisplay(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}
function toggleStepUp() {
  const on = document.getElementById("stepUpToggle").checked;
  document.getElementById("stepUpGroup").classList.toggle("hidden", !on);
}
function applySipPreset(val) {
  if (!val) return;
  const rEl = document.getElementById("sipRet");
  const sEl = document.getElementById("sipRetSlider");
  const dEl = document.getElementById("sipRetDisplay");
  if (rEl) rEl.value = val;
  if (sEl) sEl.value = val;
  if (dEl) dEl.textContent = val + "%";
}

async function calculateSIP() {
  const sipAmt = parseFloat(document.getElementById("sipAmt").value);
  const sipYrs = parseInt(document.getElementById("sipYrs").value);
  const sipRet = parseFloat(document.getElementById("sipRet").value);
  const stepUpOn = document.getElementById("stepUpToggle").checked;
  const stepUpVal = stepUpOn ? parseFloat(document.getElementById("stepUp").value) : 0;
  try {
    const res = await fetch(`${API}/api/sip/calculate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ monthly_amount: sipAmt, years: sipYrs, expected_return_pct: sipRet, step_up_pct: stepUpVal })
    });
    const data = await res.json();
    renderSipResults(data);
  } catch (e) {
    renderSipResults(computeSIPClientSide(sipAmt, sipYrs, sipRet, stepUpVal));
  }
}

function computeSIPClientSide(monthly, years, ret, stepUp) {
  const r = ret / 100 / 12, su = stepUp / 100;
  let corpus = 0, invested = 0, m = monthly;
  const timeline = [];
  for (let yr = 1; yr <= years; yr++) {
    if (yr > 1 && su > 0) m *= (1 + su);
    for (let mo = 0; mo < 12; mo++) { corpus = (corpus + m) * (1 + r); invested += m; }
    timeline.push({ year: yr, invested: Math.round(invested), corpus: Math.round(corpus), wealth_gained: Math.round(corpus - invested) });
  }
  const scenarios = [{ label: "Conservative", return_pct: 8 }, { label: "Moderate", return_pct: 12 }, { label: "Aggressive", return_pct: 16 }].map(s => {
    const sr = s.return_pct / 100 / 12; let c = 0, inv = 0, sm = monthly;
    for (let yr = 0; yr < years; yr++) {
      if (yr > 0 && su > 0) sm *= (1 + su);
      for (let mo = 0; mo < 12; mo++) { c = (c + sm) * (1 + sr); inv += sm; }
    }
    return { ...s, maturity_value: Math.round(c), total_invested: Math.round(inv), wealth_gained: Math.round(c - inv) };
  });
  return { monthly_amount: monthly, years, expected_return_pct: ret, step_up_pct: stepUp, total_invested: Math.round(invested), maturity_value: Math.round(corpus), wealth_gained: Math.round(corpus - invested), timeline, scenarios };
}

function renderSipResults(data) {
  const fmt = v => "₹" + Math.round(v).toLocaleString("en-IN");
  const wPct = data.total_invested > 0 ? ((data.wealth_gained / data.total_invested) * 100).toFixed(0) : 0;
  document.getElementById("sipResults").innerHTML = `
    <div class="results-metrics">
      <div class="result-metric-card"><div class="rm-label">Total Invested</div><div class="rm-value">${fmt(data.total_invested)}</div><div class="rm-sub">Over ${data.years} years</div></div>
      <div class="result-metric-card"><div class="rm-label">Maturity Value</div><div class="rm-value primary">${fmt(data.maturity_value)}</div><div class="rm-sub">At ${data.expected_return_pct}% CAGR</div></div>
      <div class="result-metric-card"><div class="rm-label">Wealth Gained</div><div class="rm-value secondary">${fmt(data.wealth_gained)}</div><div class="rm-sub">+${wPct}% on investment</div></div>
      <div class="result-metric-card"><div class="rm-label">Monthly SIP</div><div class="rm-value">₹${Math.round(data.monthly_amount).toLocaleString("en-IN")}</div><div class="rm-sub">${data.step_up_pct > 0 ? "+" + data.step_up_pct + "% step-up/yr" : "Fixed SIP"}</div></div>
    </div>
    <div class="chart-card-sip"><h3>📈 Wealth Growth Projection</h3><div class="sip-chart-wrap"><canvas id="sipChart"></canvas></div></div>
    <div>
      <h3 style="font-family:var(--font-headline);font-size:18px;font-weight:700;margin-bottom:14px">🎯 Scenario Comparison</h3>
      <div class="scenario-grid">
        ${data.scenarios.map(s => `
          <div class="scenario-card ${s.label.toLowerCase()}">
            <div class="sc-label ${s.label.toLowerCase()}">${s.label}</div>
            <div class="sc-return">Assumed return: ${s.return_pct}% p.a.</div>
            <div class="sc-maturity">${fmt(s.maturity_value)}</div>
            <div class="sc-gained">Gains: ${fmt(s.wealth_gained)}</div>
          </div>`).join("")}
      </div>
    </div>
    <div class="timeline-table-wrap">
      <h3>📅 Year-by-Year Breakdown</h3>
      <div style="overflow-x:auto">
        <table class="timeline-table">
          <thead><tr><th>Year</th><th>Total Invested</th><th>Corpus Value</th><th>Wealth Gained</th><th>Multiplier</th></tr></thead>
          <tbody>
            ${data.timeline.map(t => `<tr>
              <td>Year ${t.year}</td><td>${fmt(t.invested)}</td>
              <td class="tl-corpus">${fmt(t.corpus)}</td>
              <td class="tl-gained">${fmt(t.wealth_gained)}</td>
              <td>${t.invested > 0 ? (t.corpus/t.invested).toFixed(2) : "1.00"}x</td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
  setTimeout(() => {
    const ctx = document.getElementById("sipChart");
    if (!ctx) return;
    if (projChart) projChart.destroy();
    projChart = new Chart(ctx.getContext("2d"), {
      type: "line",
      data: {
        labels: data.timeline.map(t => "Y" + t.year),
        datasets: [
          { label: "Corpus Value", data: data.timeline.map(t => t.corpus), borderColor: "#a8e8ff", backgroundColor: "rgba(168,232,255,0.08)", fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2 },
          { label: "Amount Invested", data: data.timeline.map(t => t.invested), borderColor: "rgba(133,147,152,0.6)", backgroundColor: "rgba(133,147,152,0.04)", fill: true, tension: 0.4, pointRadius: 0, borderWidth: 1, borderDash: [4,4] }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { color: "#bbc9cf", font: { size: 11 }, boxWidth: 12 } },
          tooltip: { backgroundColor: "#1a1c20", borderColor: "rgba(60,73,78,0.3)", borderWidth: 1,
            callbacks: { label: c => `${c.dataset.label}: ₹${Math.round(c.raw).toLocaleString("en-IN")}` } }
        },
        scales: {
          x: { grid: { color: "rgba(60,73,78,0.1)" }, ticks: { color: "#859398", maxTicksLimit: 10 } },
          y: { grid: { color: "rgba(60,73,78,0.1)" }, ticks: { color: "#859398",
            callback: v => "₹" + (v >= 1e7 ? (v/1e7).toFixed(1) + "Cr" : v >= 1e5 ? (v/1e5).toFixed(1) + "L" : v) } }
        }
      }
    });
  }, 50);
}

// ============================================================================
// COMPANY INTELLIGENCE MODULE
// ============================================================================

let coChart = null;
let _coData = null;

function handleCompanySearchInput() {
  // Suggestions handled by existing ticker search logic — no-op here, search fires on Enter
}

async function loadCompany() {
  const input = document.getElementById("companySearchInput");
  if (!input) return;
  const ticker = input.value.trim().toUpperCase();
  if (!ticker) return;

  document.getElementById("coEmpty").style.display = "none";
  document.getElementById("coLoading").style.display = "block";
  const content = document.getElementById("companyContent");
  content.classList.remove("visible");

  try {
    const res = await fetch(`${API}/api/company/${encodeURIComponent(ticker)}`);
    if (!res.ok) throw new Error("Not found");
    const d = await res.json();
    _coData = d;
    renderCompany(d);
  } catch (e) {
    // Fallback: use existing stock summary API
    try {
      const res2 = await fetch(`${API}/api/stock/summary/${encodeURIComponent(ticker)}`);
      const d2 = await res2.json();
      renderCompanyFromSummary(d2, ticker);
    } catch (e2) {
      document.getElementById("coLoading").style.display = "none";
      document.getElementById("coEmpty").style.display = "block";
      document.getElementById("coEmpty").innerHTML = `
        <div class="co-empty"><div class="icon">⚠</div>
        <h3>Company Not Found</h3>
        <p>Try adding .NS (NSE) or .BO (BSE) suffix. Example: RELIANCE.NS</p></div>`;
    }
  }
}

function loadCompanyDirect(ticker) {
  navigateTo("company");
  const el = document.getElementById("companySearchInput");
  if (el) { el.value = ticker; loadCompany(); }
}

function renderCompanyFromSummary(d, ticker) {
  document.getElementById("coLoading").style.display = "none";
  const content = document.getElementById("companyContent");
  content.classList.add("visible");

  const price = d.price || 0;
  const change = d.change_pct || 0;
  const isUp = change >= 0;
  const name = d.company_name || ticker;

  document.getElementById("coHeaderBar").innerHTML = `
    <div>
      <div class="co-badge-row">
        <span class="co-badge badge-primary">${d.exchange || "NSE"}</span>
        <span class="co-badge badge-outline">${d.sector || "Equity"}</span>
      </div>
      <div class="co-name">${name}</div>
      <div class="co-desc">${d.industry || ""} · ${ticker}</div>
    </div>
    <div class="co-header-right">
      <div class="co-price" style="color:${isUp?"var(--secondary)":"var(--on-tertiary-cont)"}">₹${price.toLocaleString("en-IN")}</div>
      <div class="co-change" style="color:${isUp?"var(--secondary)":"var(--on-tertiary-cont)"}">${isUp?"+":""}${change.toFixed(2)}%</div>
      <div class="co-mktcap">Market Cap: ${d.market_cap_fmt || "—"}</div>
    </div>
  `;

  // Asset grid
  const info = d.info || {};
  document.getElementById("coAssetGrid").innerHTML = [
    { icon: "📊", label: "P/E Ratio", value: d.pe_ratio ? d.pe_ratio.toFixed(1) : "—", sub: "Price / Earnings" },
    { icon: "📈", label: "EPS (TTM)", value: d.eps ? "₹" + d.eps.toFixed(2) : "—", sub: "Earnings Per Share" },
    { icon: "🏦", label: "52W High", value: d.week_52_high ? "₹" + d.week_52_high.toFixed(2) : "—", sub: "Yearly high" },
    { icon: "📉", label: "52W Low", value: d.week_52_low ? "₹" + d.week_52_low.toFixed(2) : "—", sub: "Yearly low" },
    { icon: "💰", label: "Dividend Yield", value: d.dividend_yield ? d.dividend_yield.toFixed(2) + "%" : "—", sub: "Annual yield" },
    { icon: "📦", label: "Volume", value: d.volume ? (d.volume/1e5).toFixed(1) + "L" : "—", sub: "Shares today" },
  ].map(c => `
    <div class="asset-card">
      <div class="asset-icon">${c.icon}</div>
      <div class="asset-label">${c.label}</div>
      <div class="asset-value">${c.value}</div>
      <div class="asset-sub">${c.sub}</div>
    </div>
  `).join("");

  // Analyst card
  document.getElementById("coAnalystCard").innerHTML = `
    <h3><span class="material-symbols-outlined" style="font-size:16px">track_changes</span> ANALYST CONSENSUS</h3>
    <div class="analyst-target" style="color:var(--primary)">₹${d.week_52_high ? Math.round(d.week_52_high * 1.12).toLocaleString("en-IN") : "—"}</div>
    <div class="analyst-upside">Target Estimate</div>
    <div class="analyst-rec">Based on 52W High + 12%</div>
    <div class="analyst-count">Use long-term analysis for precise targets</div>
    <div class="rec-bar"><div class="rec-bar-fill" style="width:65%"></div></div>
  `;

  // Vitals
  document.getElementById("coVitalsList").innerHTML = [
    { label: "Beta", value: d.beta ? d.beta.toFixed(2) : "—" },
    { label: "ROE", value: d.roe ? d.roe.toFixed(1) + "%" : "—", green: d.roe && d.roe > 15 },
    { label: "D/E Ratio", value: d.debt_to_equity ? d.debt_to_equity.toFixed(2) : "—" },
    { label: "Profit Margin", value: d.profit_margin ? (d.profit_margin*100).toFixed(1) + "%" : "—", green: d.profit_margin && d.profit_margin > 0.1 },
  ].map(r => `
    <div class="vital-row">
      <span class="vital-label">${r.label}</span>
      <span class="vital-value ${r.green ? "green" : ""}">${r.value}</span>
    </div>
  `).join("");

  // 52W range card
  const h = d.week_52_high || 0, l = d.week_52_low || 0, p = price;
  const pct = h > l ? Math.min(100, Math.max(0, ((p - l)/(h - l)) * 100)) : 50;
  document.getElementById("co52wCard").innerHTML = `
    <div class="sidebar-card-header" style="margin-bottom:12px"><h3>📍 52-Week Range</h3></div>
    <div class="range-52w">
      <div class="range-52w-label">₹${l.toFixed(0)}</div>
      <div class="range-52w-bar">
        <div class="range-52w-fill" style="width:${pct}%"></div>
        <div class="range-52w-marker" style="left:${pct}%"></div>
      </div>
      <div class="range-52w-label">₹${h.toFixed(0)}</div>
    </div>
    <div style="text-align:center;margin-top:10px;font-size:12px;color:var(--on-surf-var)">Current ₹${p.toLocaleString("en-IN")} — ${pct.toFixed(0)}% of 52W range</div>
    <button onclick="navigateTo('markets');document.getElementById('tickerInput').value='${ticker}';loadTicker()" style="width:100%;margin-top:14px;padding:10px;background:linear-gradient(135deg,var(--primary),var(--primary-cont));color:var(--on-primary);font-family:var(--font-headline);font-size:12px;font-weight:700;border:none;border-radius:var(--radius);cursor:pointer;">📈 View Chart & Full Analysis →</button>
  `;

  // Real historical chart for the company
  buildCoBarChart(name, price, d.week_52_high, d.week_52_low, ticker);
}

function renderCompany(d) {
  // Full company API response
  renderCompanyFromSummary(d, d.ticker || "");
}

async function buildCoBarChart(name, price, high, low, ticker) {
  const canvas = document.getElementById("coChart");
  if (!canvas) return;
  if (coChart) coChart.destroy();

  // Try to fetch real historical data from backend
  let labels = [];
  let prices = [];
  let volumes = [];
  let usedReal = false;

  if (ticker) {
    try {
      const res = await fetch(`${API}/api/chart/${encodeURIComponent(ticker)}?timeframe=1y`);
      const data = await res.json();
      if (data.data && data.data.length > 0) {
        labels  = data.data.map(p => p.time);
        prices  = data.data.map(p => p.close);
        volumes = data.data.map(p => p.volume);
        usedReal = true;
      }
    } catch(e) { console.warn("Co chart fetch failed, no fallback generated", e); }
  }

  if (!usedReal || prices.length === 0) return; // Skip if no real data

  const isUp = prices[prices.length - 1] >= prices[0];
  const lineColor = isUp ? "#a8e8ff" : "#ef4444";
  const fillColor = isUp ? "rgba(168,232,255,0.07)" : "rgba(239,68,68,0.07)";

  coChart = new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: name,
        data: prices,
        borderColor: lineColor,
        backgroundColor: fillColor,
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0f1117",
          borderColor: "rgba(168,232,255,0.2)",
          borderWidth: 1,
          callbacks: {
            label: (ctx) => `₹${Number(ctx.raw).toLocaleString("en-IN")}`,
          },
        },
      },
      scales: {
        x: { grid: { color: "rgba(60,73,78,0.1)" }, ticks: { color: "#859398", maxTicksLimit: 8, maxRotation: 0, font: { size: 9 } } },
        y: { grid: { color: "rgba(60,73,78,0.1)" }, ticks: { color: "#859398", font: { size: 9 }, callback: v => "₹" + (v >= 1e5 ? (v/1e5).toFixed(1)+"L" : Number(v).toLocaleString("en-IN")) } }
      }
    }
  });
}

function switchCoChart(type, btn) {
  document.querySelectorAll(".chart-tab-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  if (_coData) {
    const ticker = _coData.ticker || document.getElementById("companySearchInput")?.value?.trim()?.toUpperCase() || "";
    buildCoBarChart(_coData.company_name || "Stock", _coData.price, _coData.week_52_high, _coData.week_52_low, ticker);
  }
}

// ============================================================================
// MONTHLY INVESTMENT BRIEF MODULE
// ============================================================================

let _briefLoaded = false;
let _briefData   = null;

// Signal → color + emoji mapping
const SIGNAL_META = {
  "SIP CONTINUE":  { color: "var(--secondary)",          bg: "rgba(64,229,108,0.12)",   emoji: "✅" },
  "LUMP SUM BUY":  { color: "#a855f7",                   bg: "rgba(168,85,247,0.12)",   emoji: "💰" },
  "SIP PAUSE":     { color: "#eab308",                   bg: "rgba(234,179,8,0.12)",    emoji: "⏸" },
  "SIP REDUCE":    { color: "#f97316",                   bg: "rgba(249,115,22,0.12)",   emoji: "⬇" },
  "EXIT":          { color: "var(--on-tertiary-cont)",   bg: "rgba(163,0,38,0.12)",     emoji: "🚨" },
  "HOLD (Lock-in)":{ color: "#64748b",                   bg: "rgba(100,116,139,0.12)",  emoji: "🔒" },
};

const DIR_META = {
  "BULLISH": { color: "var(--secondary)", label: "📈 Bullish" },
  "NEUTRAL": { color: "#eab308",          label: "➡ Neutral"  },
  "BEARISH": { color: "var(--on-tertiary-cont)", label: "📉 Bearish" },
};

function signalBadge(signal) {
  const m = SIGNAL_META[signal] || { color: "var(--outline)", bg: "rgba(133,147,152,0.1)", emoji: "•" };
  return `<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:700;background:${m.bg};color:${m.color}">${m.emoji} ${signal}</span>`;
}

function dirBadge(dir) {
  const m = DIR_META[dir] || { color: "var(--outline)", label: dir };
  return `<span style="font-size:11px;font-weight:700;color:${m.color}">${m.label}</span>`;
}

function gateBadge(gate) {
  return gate === "PASS"
    ? `<span style="padding:2px 8px;border-radius:3px;background:rgba(64,229,108,0.1);color:var(--secondary);font-size:10px;font-weight:700">✓ PASS</span>`
    : `<span style="padding:2px 8px;border-radius:3px;background:rgba(163,0,38,0.1);color:var(--on-tertiary-cont);font-size:10px;font-weight:700">✗ FAIL</span>`;
}

// ── Render the full monthly brief ─────────────────────────────────────────
function renderMonthlyBrief(brief) {
  _briefData   = brief;
  const el     = document.getElementById("mfBriefPanel");
  if (!el) return;

  const systemic = brief.guardrails?.systemic_risk_flag;

  el.innerHTML = `
    <!-- Header -->
    <div class="brief-header">
      <div>
        <div class="brief-title">📋 Monthly Investment Brief</div>
        <div class="brief-subtitle">${brief.report_month} · Model Confidence: <strong style="color:var(--primary)">${brief.model_confidence_avg}%</strong></div>
      </div>
      <button class="brief-refresh-btn" onclick="loadFundBrief(true)">⟳ Refresh</button>
    </div>

    ${systemic ? `
    <div class="brief-alert-banner">
      ⚠ SYSTEMIC RISK ALERT — ${brief.guardrails.exit_signal_count} funds triggered EXIT signals simultaneously.
      Consider moving 50% of portfolio to liquid funds pending review.
    </div>` : ""}

    <!-- Executive Summary -->
    <div class="brief-section">
      <div class="brief-section-title">Executive Summary</div>
      <p class="brief-exec">${brief.executive_summary}</p>
    </div>

    <!-- Macro Commentary -->
    <div class="brief-macro">
      <div class="brief-section-title">🌍 Macro Commentary</div>
      <div class="macro-chips">
        <div class="macro-chip"><span class="mc-label">RBI Repo</span><span class="mc-val">${brief.macro_inputs.repo_rate}%</span></div>
        <div class="macro-chip"><span class="mc-label">CPI Inflation</span><span class="mc-val">${brief.macro_inputs.cpi}%</span></div>
        <div class="macro-chip"><span class="mc-label">Nifty P/E</span><span class="mc-val">${brief.macro_inputs.nifty_pe}x</span></div>
        <div class="macro-chip"><span class="mc-label">Confidence</span><span class="mc-val" style="color:var(--primary)">${brief.model_confidence_avg}%</span></div>
      </div>
      <p class="brief-macro-text">${brief.macro_commentary}</p>
    </div>

    <!-- Top SIP Opportunities -->
    ${brief.top_sip_opportunities?.length ? `
    <div class="brief-section">
      <div class="brief-section-title">🏆 Top 3 SIP Opportunities</div>
      <div class="brief-opportunities">
        ${brief.top_sip_opportunities.map((f, i) => `
          <div class="opp-card" style="border-left:3px solid ${["var(--primary)","var(--secondary)","#a855f7"][i]||"var(--outline)"}">
            <div class="opp-rank">#${i+1}</div>
            <div class="opp-main">
              <div class="opp-name">${f.fund}</div>
              <div class="opp-meta">${f.category} · Min SIP ₹${f.min_sip} · ${f.risk_rating}</div>
              <div class="opp-rationale">${f.rationale}</div>
            </div>
            <div class="opp-right">
              <div class="opp-forecast">+${f.forecast_12m}%</div>
              <div class="opp-forecast-label">12M forecast</div>
              <div style="margin-top:6px">${signalBadge(f.signal)}</div>
              <div style="margin-top:6px;font-size:10px;color:var(--outline)">Confidence: ${f.confidence_pct}%</div>
            </div>
          </div>
        `).join("")}
      </div>
    </div>` : ""}

    <!-- Fund Signal Table -->
    <div class="brief-section">
      <div class="brief-section-title">📊 Fund Signal Table</div>
      <div class="brief-table-wrap">
        <table class="brief-table">
          <thead>
            <tr>
              <th>Fund</th><th>Category</th><th>12M Forecast</th>
              <th>Direction</th><th>Fundamentals</th><th>Risk</th><th>Signal</th><th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${(brief.fund_signal_table || []).map(f => `
              <tr>
                <td style="font-weight:700;color:var(--on-surface);max-width:160px;word-break:break-word">${f.fund}</td>
                <td><span style="font-size:10px;padding:2px 6px;background:var(--bg-highest);border-radius:3px;color:var(--on-surf-var)">${f.category}</span></td>
                <td style="font-family:var(--font-headline);font-weight:700;color:${f.forecast_12m >= 12 ? "var(--secondary)" : f.forecast_12m >= 6 ? "#eab308" : "var(--on-tertiary-cont)"}">${f.forecast_12m > 0 ? "+" : ""}${f.forecast_12m}%</td>
                <td>${dirBadge(f.direction)}</td>
                <td>${gateBadge(f.fundamental_gate)}</td>
                <td style="font-size:12px;color:var(--on-surf-var)">${f.risk_rating}</td>
                <td>${signalBadge(f.signal)}</td>
                <td style="font-size:11px;color:var(--on-surf-var);max-width:180px">${f.action}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Pause / Exit Funds -->
    ${brief.pause_or_exit?.length ? `
    <div class="brief-section">
      <div class="brief-section-title">⚠ Funds on Watch / Pause / Exit</div>
      <div class="brief-caution-list">
        ${brief.pause_or_exit.map(f => `
          <div class="caution-card">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
              ${signalBadge(f.signal)}
              <span style="font-weight:700;color:var(--on-surface)">${f.fund}</span>
            </div>
            <div style="font-size:11px;color:var(--on-surf-var);line-height:1.6">${f.reason}</div>
            <div style="margin-top:6px;font-style:italic;font-size:11px;color:var(--outline)">→ ${f.action}</div>
          </div>
        `).join("")}
      </div>
    </div>` : ""}

    <!-- Guardrail Notes -->
    <div class="brief-section">
      <div class="brief-section-title">🛡 Portfolio Guardrails</div>
      <div class="brief-guardrails">
        ${(brief.guardrails?.guardrail_notes || []).map(n => `
          <div class="guardrail-note">${n}</div>
        `).join("")}
      </div>
    </div>

    <!-- Disclaimer -->
    <div class="brief-disclaimer">${brief.disclaimer}</div>
  `;
}

// ── Load brief (lazy, cached) ─────────────────────────────────────────────
async function loadFundBrief(forceRefresh = false) {
  if (_briefLoaded && !forceRefresh && _briefData) {
    renderMonthlyBrief(_briefData);
    return;
  }

  const el = document.getElementById("mfBriefPanel");
  if (!el) return;

  el.innerHTML = `
    <div style="text-align:center;padding:40px 0;color:var(--outline)">
      <div class="neural-dots" style="justify-content:center;display:flex;gap:6px;margin-bottom:16px">
        <span style="width:8px;height:8px;border-radius:50%;background:var(--primary);animation:pulse 1.2s ease-in-out infinite"></span>
        <span style="width:8px;height:8px;border-radius:50%;background:var(--primary);animation:pulse 1.2s ease-in-out 0.2s infinite"></span>
        <span style="width:8px;height:8px;border-radius:50%;background:var(--primary);animation:pulse 1.2s ease-in-out 0.4s infinite"></span>
      </div>
      <div style="font-family:var(--font-headline);font-size:15px;color:var(--on-surf-var);margin-bottom:6px">Running 3-Layer Analysis</div>
      <div style="font-size:12px">Fetching NAV history · Computing Piotroski F-Score · Altman Z-Score · GBM forecast…</div>
      <div style="font-size:11px;margin-top:10px;color:var(--outline)">This may take 30–60 seconds</div>
    </div>`;

  try {
    const res  = await fetch(`${API}/api/mutual-funds/brief`);
    const data = await res.json();
    _briefLoaded = true;
    renderMonthlyBrief(data);
  } catch (e) {
    el.innerHTML = `<div style="padding:24px;color:var(--on-tertiary-cont);text-align:center">
      ⚠ Backend offline or analysis failed.<br>
      <span style="font-size:12px;color:var(--outline)">Start the FastAPI server and try again.</span>
      <br><button onclick="loadFundBrief(true)" style="margin-top:12px;padding:8px 16px;background:var(--bg-high);color:var(--primary);border:1px solid rgba(168,232,255,0.2);border-radius:6px;cursor:pointer;font-family:var(--font-headline)">Retry</button>
    </div>`;
  }
}

// ============================================================================
// WALLET FUNCTIONS
// ============================================================================

let walletBalance = 1000000.00; // Initial wallet balance (synced with backend)


function showWallet() {
  document.getElementById("walletPanel").classList.remove("hidden");
  document.getElementById("walletActionArea").innerHTML = "";
  document.getElementById("walletMessage").classList.add("hidden");
  loadWalletBalance();
  loadWalletTransactions();
}

function closeWallet() {
  document.getElementById("walletPanel").classList.add("hidden");
}

async function loadWalletBalance() {
  try {
    const res = await fetch(`${API}/api/wallet/balance`);
    const data = await res.json();
    if (data.balance !== undefined) {
      walletBalance = data.balance;
      document.getElementById("walletBalance").textContent = "₹" + formatNumber(walletBalance);
      // Sync portfolio cash balance display
      const portBalanceEl = document.getElementById("portBalance");
      if (portBalanceEl) portBalanceEl.textContent = "₹" + formatNumber(walletBalance);
    }
  } catch (e) {
    console.error("Error loading wallet balance:", e);
    document.getElementById("walletBalance").textContent = "₹" + formatNumber(walletBalance);
  }
}

async function loadWalletTransactions() {
  try {
    const res = await fetch(`${API}/api/wallet/transactions`);
    const data = await res.json();
    const list = document.getElementById("walletTxnList");
    if (!data.transactions || data.transactions.length === 0) {
      list.innerHTML = '<div class="wallet-txn-empty">No transactions yet</div>';
      return;
    }
    list.innerHTML = data.transactions.slice(-10).reverse().map(txn => {
      const date = new Date(txn.timestamp);
      const dateStr = date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' }) + ' ' +
        date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
      const sign = txn.type === 'credit' ? '+' : '-';
      return `
        <div class="wallet-txn-item">
          <div class="wallet-txn-left">
            <span class="wallet-txn-type ${txn.type}">${txn.type === 'credit' ? '↓ Deposit' : '↑ Withdrawal'}</span>
            <span class="wallet-txn-date">${dateStr}</span>
          </div>
          <span class="wallet-txn-amount" style="color: ${txn.type === 'credit' ? '#22c55e' : '#ef4444'}">${sign}₹${formatNumber(txn.amount)}</span>
        </div>
      `;
    }).join("");
  } catch (e) {
    console.error("Error loading transactions:", e);
  }
}

function showAddMoney() {
  document.getElementById("walletActionArea").innerHTML = `
    <div class='wallet-form'>
      <h3>Add Money</h3>
      <input type='number' id='addAmount' placeholder='Enter amount (₹)' min='1' />
      <button onclick='startRazorpayPayment()'>Pay with Razorpay</button>
    </div>
  `;
  document.getElementById("walletMessage").classList.add("hidden");
}

function showWithdrawMoney() {
  document.getElementById("walletActionArea").innerHTML = `
    <div class='wallet-form'>
      <h3>Withdraw Money</h3>
      <input type='number' id='withdrawAmount' placeholder='Enter amount (₹)' min='1' />
      <button onclick='startWithdraw()'>Withdraw to Bank</button>
    </div>
  `;
  document.getElementById("walletMessage").classList.add("hidden");
}

function showWalletMessage(message, type = 'success') {
  const msgEl = document.getElementById("walletMessage");
  msgEl.textContent = message;
  msgEl.className = `wallet-message ${type}`;
  msgEl.classList.remove("hidden");
  setTimeout(() => { msgEl.classList.add("hidden"); }, 5000);
}

function quickAdd(amount) {
  // Pre-fill the add money form and trigger Razorpay
  showAddMoney();
  setTimeout(() => {
    const input = document.getElementById('addAmount');
    if (input) input.value = amount;
    startRazorpayPayment();
  }, 100);
}

// Razorpay integration
function startRazorpayPayment() {
  const amt = document.getElementById('addAmount').value;
  if (!amt || amt <= 0) {
    showWalletMessage('Please enter a valid amount', 'error');
    return;
  }

  const amountInPaise = Math.round(parseFloat(amt) * 100);

  const options = {
    key: 'rzp_test_SDdi0bRwia1AA4',
    amount: amountInPaise,
    currency: 'INR',
    name: 'AarthiAI Wallet',
    description: 'Add Money to Wallet',
    handler: function (response) {
      verifyAndCreditWallet(response.razorpay_payment_id, parseFloat(amt));
    },
    prefill: {
      name: 'User',
      email: 'user@example.com'
    },
    theme: {
      color: '#22c55e'
    },
    modal: {
      ondismiss: function () {
        showWalletMessage('Payment cancelled', 'error');
      }
    }
  };

  try {
    const rzp = new Razorpay(options);
    rzp.open();
  } catch (e) {
    console.error("Razorpay error:", e);
    showWalletMessage('Payment gateway error. Please try again.', 'error');
  }
}

async function verifyAndCreditWallet(paymentId, amount) {
  try {
    const res = await fetch(`${API}/api/wallet/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payment_id: paymentId, amount: amount })
    });

    const data = await res.json();

    if (res.ok && data.status === 'success') {
      walletBalance = data.new_balance;
      document.getElementById("walletBalance").textContent = "₹" + formatNumber(walletBalance);
      // Sync portfolio cash balance
      const portBalanceEl = document.getElementById("portBalance");
      if (portBalanceEl) portBalanceEl.textContent = "₹" + formatNumber(walletBalance);
      showWalletMessage(`✅ ₹${formatNumber(amount)} added successfully!`, 'success');
      document.getElementById("walletActionArea").innerHTML = "";
      loadWalletTransactions();
    } else {
      showWalletMessage(data.detail || 'Payment verification failed. Contact support.', 'error');
    }
  } catch (e) {
    console.error("Wallet credit error:", e);
    showWalletMessage('Network error. Please check your connection and try again.', 'error');
  }
}

async function startWithdraw() {
  const amt = document.getElementById('withdrawAmount').value;
  if (!amt || amt <= 0) {
    showWalletMessage('Please enter a valid amount', 'error');
    return;
  }

  const withdrawAmount = parseFloat(amt);

  if (withdrawAmount > walletBalance) {
    showWalletMessage('Insufficient balance', 'error');
    return;
  }

  if (!confirm(`Withdraw ₹${formatNumber(withdrawAmount)} from your wallet?`)) {
    return;
  }

  try {
    const res = await fetch(`${API}/api/wallet/withdraw`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount: withdrawAmount })
    });

    const data = await res.json();

    if (res.ok && data.status === 'success') {
      walletBalance = data.new_balance;
      document.getElementById("walletBalance").textContent = "₹" + formatNumber(walletBalance);
      // Sync portfolio cash balance
      const portBalanceEl = document.getElementById("portBalance");
      if (portBalanceEl) portBalanceEl.textContent = "₹" + formatNumber(walletBalance);
      showWalletMessage(`✅ ₹${formatNumber(withdrawAmount)} withdrawn successfully!`, 'success');
      document.getElementById("walletActionArea").innerHTML = "";
      loadWalletTransactions();
    } else {
      showWalletMessage(data.detail || 'Withdrawal failed', 'error');
    }
  } catch (e) {
    console.error("Withdrawal error:", e);
    showWalletMessage('Network error. Please check your connection and try again.', 'error');
  }
}


// ============================================================================
// MAIN APP CODE
// ============================================================================

// (API constant defined at top of file)

let currentTicker = "";
let liveInterval = null;
let portfolioInterval = null;
let mainChart = null;
let volumeChart = null;
let predChart = null;
let activeTimeframe = "1d";
let loadVersion = 0;



let searchTimeout = null;

// ── Forecast tab switcher ────────────────────────────────────────────────────
function switchForecastTab(el, tab) {
  document.querySelectorAll(".forecast-tab").forEach(t => t.classList.remove("active"));
  el.classList.add("active");

  const predSection = document.getElementById("predSection");
  const ltPanel = document.getElementById("ltPanel");

  if (tab === "long") {
    predSection.classList.add("hidden");
    ltPanel.classList.remove("hidden");
    if (currentTicker) loadLongTerm(currentTicker);
  } else {
    // 5d forecast
    ltPanel.classList.add("hidden");
    if (currentTicker) predSection.classList.remove("hidden");
  }
}

// ── Long-Term Analysis ───────────────────────────────────────────────────────
let _ltLoaded = null;  // ticker last loaded

async function loadLongTerm(ticker) {
  if (!ticker) return;

  const loader  = document.getElementById("ltLoader");
  const results = document.getElementById("ltResults");
  loader.style.display = "block";
  results.classList.add("hidden");

  try {
    const res = await fetch(`${API}/api/long-term/${ticker}`);
    if (!res.ok) throw new Error(await res.text());
    const d = await res.json();
    renderLongTerm(d);
    _ltLoaded = ticker;
  } catch(e) {
    loader.innerHTML = `<p style="color:var(--on-tertiary-cont);font-size:13px;">⚠ Analysis failed: ${e.message}</p>`;
  }
}

function renderLongTerm(d) {
  const loader  = document.getElementById("ltLoader");
  const results = document.getElementById("ltResults");

  // Score ring animation (circumference = 2π×34 ≈ 213.6)
  const circ = 213.6;
  const fill  = (d.composite_score / 10) * circ;
  const arc = document.getElementById("ltRingArc");
  // Color by verdict
  const ringColor = d.composite_score >= 8 ? "#40e56c" : d.composite_score >= 6 ? "#a8e8ff" : d.composite_score >= 4 ? "#eab308" : "#a30026";
  arc.setAttribute("stroke", ringColor);
  setTimeout(() => arc.setAttribute("stroke-dasharray", `${fill} ${circ}`), 100);

  document.getElementById("ltScoreNum").textContent = d.composite_score.toFixed(1);

  // Verdict
  const vEl = document.getElementById("ltVerdict");
  vEl.textContent = d.verdict;
  vEl.className = "lt-verdict " + (
    d.composite_score >= 8.5 ? "verdict-hc" :
    d.composite_score >= 7   ? "verdict-buy" :
    d.composite_score >= 5.5 ? "verdict-watch" : "verdict-avoid"
  );

  document.getElementById("ltSector").textContent = `Sector: ${d.sector.toUpperCase()} · Updated quarterly`;
  document.getElementById("ltPosSize").textContent = `📐 Position: ${d.position_size}`;

  // Key insights
  const si = document.getElementById("ltStrongest");
  si.innerHTML = `<span class="chip-label">💪 Strongest Signal</span>${d.key_insight.strongest}`;
  const wi = document.getElementById("ltWeakest");
  wi.innerHTML = `<span class="chip-label">⚠ Biggest Risk</span>${d.key_insight.biggest_risk}`;

  // Hard rejects
  const rw = document.getElementById("ltRejectsWrap");
  const rl = document.getElementById("ltRejectsList");
  if (d.hard_rejects && d.hard_rejects.length) {
    rw.classList.remove("hidden");
    rl.innerHTML = `<ul>${d.hard_rejects.map(r => `<li>${r}</li>`).join("")}</ul>`;
  } else {
    rw.classList.add("hidden");
  }

  // Pillar bars
  const pillarMeta = [
    { key: "fundamental", icon: "📊", label: "Fundamental Quality" },
    { key: "technical",   icon: "📈", label: "Technical Entry" },
    { key: "sentiment",   icon: "📰", label: "News & Sentiment" },
    { key: "ownership",   icon: "🏛", label: "Ownership & Governance" },
    { key: "growth",      icon: "🚀", label: "Growth Pipeline" },
  ];
  const pillarEl = document.getElementById("ltPillars");
  pillarEl.innerHTML = pillarMeta.map(pm => {
    const p = d.pillars[pm.key];
    const sc = p.score;
    const wt = Math.round(p.weight * 100);
    const pct = (sc / 10) * 100;
    const colorClass = sc >= 7 ? "pillar-high" : sc >= 5.5 ? "pillar-mid" : sc >= 4 ? "pillar-low" : "pillar-poor";
    const signals = (p.signals || []).slice(0, 3).map(s =>
      `<div class="lt-pillar-signal">${s}</div>`
    ).join("");
    return `
      <div class="lt-pillar">
        <div class="lt-pillar-header">
          <span class="lt-pillar-name">${pm.icon} ${pm.label}</span>
          <span>
            <span class="lt-pillar-score" style="color:${sc>=7?'var(--secondary)':sc>=5.5?'var(--primary)':sc>=4?'#eab308':'var(--on-tertiary-cont)'}">${sc.toFixed(1)}</span>
            <span class="lt-pillar-weight"> /10 · ${wt}% weight</span>
          </span>
        </div>
        <div class="lt-pillar-bar"><div class="lt-pillar-fill ${colorClass}" style="width:0%" data-pct="${pct}"></div></div>
        <div class="lt-pillar-signals">${signals}</div>
      </div>
    `;
  }).join("");

  // Animate pillar bars
  setTimeout(() => {
    document.querySelectorAll(".lt-pillar-fill").forEach(bar => {
      bar.style.width = bar.dataset.pct + "%";
    });
  }, 150);

  // Exit triggers
  document.getElementById("ltExitList").innerHTML = (d.exit_triggers || []).map(t =>
    `<div class="lt-exit-item">${t}</div>`
  ).join("");

  // Rebalance
  document.getElementById("ltRebalance").textContent = `🔄 ${d.rebalance_cadence}`;

  // ── Long-Term Price Projection Chart ───────────────────────────────────────
  drawLongTermProjectionChart(d);

  loader.style.display = "none";
  results.classList.remove("hidden");
}

// Chart instance for long-term projection
let _ltProjChart = null;

async function drawLongTermProjectionChart(d) {
  // Inject chart container if not already present
  let chartContainer = document.getElementById("ltProjChartWrap");
  if (!chartContainer) {
    const resultsEl = document.getElementById("ltResults");
    chartContainer = document.createElement("div");
    chartContainer.id = "ltProjChartWrap";
    chartContainer.style.cssText = "margin:20px 0 8px;background:rgba(10,12,18,0.6);border:1px solid rgba(60,73,78,0.25);border-radius:12px;padding:16px 16px 8px;";
    chartContainer.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <div>
          <div style="font-family:var(--font-headline,Space Grotesk),sans-serif;font-size:13px;font-weight:700;color:#bbc9cf">📈 12-Month Price Projection</div>
          <div style="font-size:11px;color:#859398;margin-top:2px">Based on 5-Pillar composite score · fundamental + technical trajectory</div>
        </div>
        <div id="ltProjBadge" style="display:flex;align-items:center;gap:6px;padding:4px 10px;border-radius:6px;font-size:11px;font-weight:700;background:rgba(168,232,255,0.08);color:#a8e8ff">
          <span style="width:6px;height:6px;border-radius:50%;background:#a8e8ff;display:inline-block"></span>
          MODEL PROJECTION
        </div>
      </div>
      <div style="position:relative;height:200px"><canvas id="ltProjChart"></canvas></div>
      <div id="ltProjMetrics" style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap"></div>
    `;
    // Insert before exit triggers section
    const exitEl = resultsEl.querySelector(".lt-exit-triggers");
    if (exitEl) resultsEl.insertBefore(chartContainer, exitEl);
    else resultsEl.appendChild(chartContainer);
  }

  // Fetch real historical price data for anchor
  let currentPrice = 0;
  let histPrices = [];
  let histLabels = [];
  try {
    const ticker = currentTicker;
    if (!ticker) return;
    const res = await fetch(`${API}/api/chart/${ticker}?timeframe=1y`);
    const cData = await res.json();
    if (cData.data && cData.data.length > 0) {
      histPrices = cData.data.map(p => p.close);
      histLabels = cData.data.map(p => p.time);
      currentPrice = histPrices[histPrices.length - 1];
    }
  } catch(e) { console.error("LT chart fetch error", e); }

  if (!currentPrice || currentPrice === 0) return;

  // Build 12-month projection from composite score
  const score = d.composite_score; // 0-10
  const techScore = (d.pillars?.technical?.score || 5) / 10;
  const fundScore = (d.pillars?.fundamental?.score || 5) / 10;
  const growthScore = (d.pillars?.growth?.score || 5) / 10;

  // Monthly expected return based on composite: maps score 0-10 → -2% to +3% monthly
  const baseMonthlyReturn = ((score / 10) * 5 - 2) / 100; // -2% to +3%
  const volatilityFactor = 1 - techScore * 0.3; // lower tech score = more volatile
  const uncertainty = (1 - fundScore) * 0.015; // fundamental uncertainty band

  const projLabels = [];
  const projBase = [];
  const projUpper = [];
  const projLower = [];

  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const now = new Date();
  let price = currentPrice;

  for (let m = 1; m <= 12; m++) {
    const d2 = new Date(now.getFullYear(), now.getMonth() + m, 1);
    projLabels.push(MONTHS[d2.getMonth()] + " '" + String(d2.getFullYear()).slice(2));

    // Mean-reverting growth with sector momentum
    const monthlyGrowth = baseMonthlyReturn + (growthScore - 0.5) * 0.005;
    price = price * (1 + monthlyGrowth);
    const band = price * uncertainty * Math.sqrt(m);

    projBase.push(parseFloat(price.toFixed(2)));
    projUpper.push(parseFloat((price + band).toFixed(2)));
    projLower.push(parseFloat((price - band).toFixed(2)));
  }

  // Use last 6 months of historical as anchor
  const anchorCount = Math.min(6, Math.floor(histPrices.length / 4));
  const anchorPrices = histPrices.slice(-anchorCount);
  const anchorLabels = histLabels.slice(-anchorCount);

  const allLabels = [...anchorLabels, ...projLabels];
  const histSet   = [...anchorPrices, ...Array(12).fill(null)];
  const projSet   = [...Array(anchorCount - 1).fill(null), anchorPrices[anchorCount - 1], ...projBase];
  const upperSet  = [...Array(anchorCount).fill(null), ...projUpper];
  const lowerSet  = [...Array(anchorCount).fill(null), ...projLower];

  const targetPrice = projBase[projBase.length - 1];
  const returnPct   = ((targetPrice - currentPrice) / currentPrice * 100).toFixed(1);
  const isPositive  = targetPrice >= currentPrice;
  const projColor   = score >= 7 ? "#40e56c" : score >= 5.5 ? "#a8e8ff" : score >= 4 ? "#eab308" : "#ef4444";

  // Badge color
  const badge = document.getElementById("ltProjBadge");
  if (badge) {
    badge.style.color = projColor;
    badge.style.background = `rgba(${isPositive ? "64,229,108" : "239,68,68"},0.1)`;
  }

  if (_ltProjChart) _ltProjChart.destroy();

  const canvas = document.getElementById("ltProjChart");
  if (!canvas) return;

  _ltProjChart = new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels: allLabels,
      datasets: [
        {
          label: "Historical Prices",
          data: histSet,
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59,130,246,0.06)",
          fill: false, tension: 0.3, pointRadius: 0, borderWidth: 2, order: 3,
        },
        {
          label: "Upper Estimate",
          data: upperSet,
          borderColor: `${projColor}22`,
          backgroundColor: `${projColor}14`,
          fill: "+1", tension: 0.4, pointRadius: 0, borderWidth: 1, borderDash: [3, 4], order: 1,
        },
        {
          label: "Lower Estimate",
          data: lowerSet,
          borderColor: `${projColor}22`,
          backgroundColor: `${projColor}14`,
          fill: false, tension: 0.4, pointRadius: 0, borderWidth: 1, borderDash: [3, 4], order: 1,
        },
        {
          label: `12M Projection (Score ${d.composite_score}/10)`,
          data: projSet,
          borderColor: projColor,
          backgroundColor: "transparent",
          fill: false, tension: 0.4,
          pointRadius: (ctx) => ctx.dataIndex === anchorCount - 1 || ctx.dataIndex === allLabels.length - 1 ? 5 : 0,
          borderWidth: 2.5, borderDash: [7, 3], order: 2,
          pointBackgroundColor: projColor,
          pointBorderColor: "#0f1117",
          pointBorderWidth: 1.5,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: {
            color: "#6b7280", font: { size: 10 },
            filter: (item) => !item.text.includes("Estimate"),
          },
        },
        tooltip: {
          backgroundColor: "#0f1117",
          borderColor: "rgba(168,232,255,0.2)",
          borderWidth: 1,
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.label.includes("Estimate")) return null;
              return `${ctx.dataset.label}: ₹${Number(ctx.raw || 0).toLocaleString("en-IN")}`;
            },
            afterBody: (items) => {
              const idx = items[0]?.dataIndex;
              if (idx !== undefined && idx >= anchorCount) {
                const u = upperSet[idx], l = lowerSet[idx];
                if (u && l) return [`Range: ₹${Number(l).toLocaleString("en-IN")} – ₹${Number(u).toLocaleString("en-IN")}`];
              }
              return [];
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#4b5563", maxTicksLimit: 10, maxRotation: 0, font: { size: 9 } },
          grid: { color: "rgba(31,41,55,0.4)" },
        },
        y: {
          ticks: {
            color: "#4b5563", font: { size: 9 },
            callback: (v) => "₹" + (v >= 1e5 ? (v/1e5).toFixed(1)+"L" : Number(v).toLocaleString("en-IN")),
          },
          grid: { color: "rgba(31,41,55,0.4)" },
        },
      },
    },
  });

  // Metrics strip
  const metricsEl = document.getElementById("ltProjMetrics");
  if (metricsEl) {
    const metricItems = [
      { label: "Current Price", value: `₹${Number(currentPrice).toLocaleString("en-IN")}`, color: "#a8e8ff" },
      { label: "12M Target", value: `₹${Number(targetPrice).toLocaleString("en-IN")}`, color: projColor },
      { label: "Expected Return", value: `${isPositive ? "+" : ""}${returnPct}%`, color: projColor },
      { label: "Composite Score", value: `${d.composite_score}/10`, color: projColor },
      { label: "Conviction", value: d.verdict.split(" ").slice(0,2).join(" "), color: projColor },
    ];
    metricsEl.innerHTML = metricItems.map(m => `
      <div style="flex:1;min-width:100px;background:rgba(255,255,255,0.03);border:1px solid rgba(60,73,78,0.2);border-radius:8px;padding:8px 10px;text-align:center">
        <div style="font-size:10px;color:#859398;margin-bottom:4px">${m.label}</div>
        <div style="font-family:var(--font-headline,Space Grotesk),sans-serif;font-size:13px;font-weight:700;color:${m.color}">${m.value}</div>
      </div>
    `).join("");
  }
}



document.addEventListener("DOMContentLoaded", () => {
  loadHighPotential();
  loadPortfolio();
  loadMarketIndices();
  loadWalletBalance();
  setupTimeframeButtons();
  updateTopbarLiveBadge();
  setInterval(updateTopbarLiveBadge, 60000);
  portfolioInterval = setInterval(loadPortfolio, 15000);
  setInterval(loadMarketIndices, 30000);

  const tickerInput = document.getElementById("tickerInput");
  const dropdown = document.getElementById("searchDropdown");

  tickerInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      dropdown.classList.add("hidden");
      loadTicker();
    }
    if (e.key === "Escape") dropdown.classList.add("hidden");
  });

  tickerInput.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    const q = tickerInput.value.trim();
    if (q.length < 1) {
      dropdown.classList.add("hidden");
      return;
    }
    searchTimeout = setTimeout(() => searchStocks(q), 250);
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-wrapper")) {
      dropdown.classList.add("hidden");
    }
  });
});


async function searchStocks(query) {
  const dropdown = document.getElementById("searchDropdown");
  try {
    const res = await fetch(`${API}/api/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();

    if (!data.results || data.results.length === 0) {
      dropdown.innerHTML = '<div class="search-no-results">No stocks found</div>';
      dropdown.classList.remove("hidden");
      return;
    }

    dropdown.innerHTML = data.results.map(s => `
      <div class="search-item" data-ticker="${s.ticker}">
        <span class="search-ticker">${s.ticker}</span>
        <span class="search-name">${s.name}</span>
      </div>
    `).join("");

    dropdown.querySelectorAll(".search-item").forEach(item => {
      item.addEventListener("click", () => {
        const ticker = item.dataset.ticker;
        document.getElementById("tickerInput").value = ticker;
        dropdown.classList.add("hidden");
        loadTicker(ticker);
      });
    });

    dropdown.classList.remove("hidden");
  } catch (e) {
    console.error("Search error:", e);
    dropdown.classList.add("hidden");
  }
}


async function loadMarketIndices() {
  try {
    const res = await fetch(`${API}/api/market-indices`);
    const data = await res.json();
    data.indices.forEach((idx) => {
      let priceEl, changeEl;
      if (idx.name === "NIFTY 50") {
        priceEl = document.getElementById("mktNiftyPrice");
        changeEl = document.getElementById("mktNiftyChange");
      } else if (idx.name === "SENSEX") {
        priceEl = document.getElementById("mktSensexPrice");
        changeEl = document.getElementById("mktSensexChange");
      }
      if (priceEl && changeEl) {
        priceEl.textContent = formatPrice(idx.price);
        const sign = idx.change >= 0 ? "+" : "";
        changeEl.textContent = `${sign}${idx.change.toFixed(2)} (${sign}${idx.change_pct}%)`;
        changeEl.className = `mkt-change ${idx.direction}`;
      }
    });
  } catch (e) {
    console.error("Market indices error:", e);
  }
}


function switchTab(tab) {
  switchMainView(tab);
}

function switchMainView(tab) {
  const chartsView = document.getElementById("chartsView");
  const tradingView = document.getElementById("tradingView");
  if (!chartsView || !tradingView) return;

  if (tab === "charts") {
    chartsView.classList.remove("hidden");
    tradingView.classList.add("hidden");
  } else {
    tradingView.classList.remove("hidden");
    chartsView.classList.add("hidden");
    loadPortfolio();
  }

  // Update sidenav active state
  document.querySelectorAll(".sidenav-link").forEach(link => link.classList.remove("active"));
}


function setupTimeframeButtons() {
  document.querySelectorAll(".tf-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tf-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeTimeframe = btn.dataset.tf;
      if (currentTicker) loadChartData(currentTicker, activeTimeframe);
    });
  });
}


async function loadTicker(ticker) {
  ticker = ticker || document.getElementById("tickerInput").value.trim().toUpperCase();
  if (!ticker) return;

  loadVersion++;
  const myVersion = loadVersion;
  currentTicker = ticker;
  document.getElementById("tickerInput").value = ticker;

  const emptyState = document.getElementById("chartEmptyState");
  if (emptyState) emptyState.style.display = "none";

  if (liveInterval) clearInterval(liveInterval);

  await Promise.all([
    loadLivePrice(ticker, myVersion),
    loadChartData(ticker, activeTimeframe, myVersion),
    loadPrediction(ticker, myVersion),
    loadSentimentAndIndicators(ticker, myVersion),
  ]);

  if (myVersion !== loadVersion) return;
  liveInterval = setInterval(() => loadLivePrice(ticker, loadVersion), 10000);
}


async function loadLivePrice(ticker, version) {
  try {
    const res = await fetch(`${API}/api/live/${ticker}`);
    if (version !== undefined && version !== loadVersion) return;
    const data = await res.json();

    document.getElementById("priceBanner").classList.remove("hidden");
    document.getElementById("bannerName").textContent = ticker;
    document.getElementById("bannerPrice").textContent = formatPrice(data.price);

    const changeEl = document.getElementById("bannerChange");
    const sign = data.change >= 0 ? "+" : "";
    changeEl.textContent = `${sign}${data.change} (${sign}${data.change_pct}%)`;
    changeEl.className = `price-change ${data.direction}`;

    document.getElementById("statHigh").textContent = formatPrice(data.day_high);
    document.getElementById("statLow").textContent = formatPrice(data.day_low);
    document.getElementById("statVol").textContent = formatVolume(data.volume);

    document.getElementById("mktStockLabel").textContent = ticker;
    document.getElementById("mktStockPrice").textContent = formatPrice(data.price);
    const mktChg = document.getElementById("mktStockChange");
    mktChg.textContent = `${sign}${data.change} (${sign}${data.change_pct}%)`;
    mktChg.className = `mkt-change ${data.direction}`;
  } catch (e) {
    console.error("Live price error:", e);
  }
}


async function loadChartData(ticker, timeframe, version) {
  try {
    const [chartRes, infoRes] = await Promise.all([
      fetch(`${API}/api/chart/${ticker}?timeframe=${timeframe}`),
      fetch(`${API}/api/stock/${ticker}`),
    ]);
    if (version !== undefined && version !== loadVersion) return;
    const chartData = await chartRes.json();
    const stockData = await infoRes.json();

    if (stockData.info) {
      const info = stockData.info;
      document.getElementById("bannerName").textContent = `${info.name} (${ticker})`;
      document.getElementById("statOpen").textContent = formatPrice(info.open);
      document.getElementById("statHigh").textContent = formatPrice(info.day_high);
      document.getElementById("statLow").textContent = formatPrice(info.day_low);
      document.getElementById("statVol").textContent = formatVolume(info.volume);
      document.getElementById("stat52H").textContent = formatPrice(info.fifty_two_week_high);
      document.getElementById("stat52L").textContent = formatPrice(info.fifty_two_week_low);
    }

    drawMainChart(chartData.data);
    drawVolumeChart(chartData.data);
  } catch (e) {
    console.error("Chart error:", e);
  }
}


function drawMainChart(data) {
  const labels = data.map((d) => d.time);
  const closes = data.map((d) => d.close);
  const highs = data.map((d) => d.high);
  const lows = data.map((d) => d.low);

  const isUp = closes[closes.length - 1] >= closes[0];
  const lineColor = isUp ? "#22c55e" : "#ef4444";
  const fillColor = isUp ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)";

  if (mainChart) mainChart.destroy();

  mainChart = new Chart(document.getElementById("mainChart").getContext("2d"), {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Close", data: closes, borderColor: lineColor, backgroundColor: fillColor, fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2 },
        { label: "High", data: highs, borderColor: "rgba(34,197,94,0.2)", borderDash: [2, 4], pointRadius: 0, borderWidth: 1, fill: false },
        { label: "Low", data: lows, borderColor: "rgba(239,68,68,0.2)", borderDash: [2, 4], pointRadius: 0, borderWidth: 1, fill: false },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#6b7280", font: { size: 11 } } },
        tooltip: { backgroundColor: "#1a1f2e", borderColor: "#242a38", borderWidth: 1, titleColor: "#fff", bodyColor: "#d1d5db" },
      },
      scales: {
        x: { ticks: { color: "#4b5563", maxTicksLimit: 10, maxRotation: 0, font: { size: 10 } }, grid: { color: "#1f2937" } },
        y: { ticks: { color: "#4b5563", font: { size: 10 } }, grid: { color: "#1f2937" } },
      },
    },
  });
}


function drawVolumeChart(data) {
  const labels = data.map((d) => d.time);
  const volumes = data.map((d) => d.volume);
  const colors = data.map((d, i) => {
    if (i === 0) return "rgba(59,130,246,0.5)";
    return d.close >= data[i - 1].close ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)";
  });

  if (volumeChart) volumeChart.destroy();

  volumeChart = new Chart(document.getElementById("volumeChart").getContext("2d"), {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Volume", data: volumes, backgroundColor: colors, borderWidth: 0 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { ticks: { color: "#4b5563", font: { size: 9 } }, grid: { color: "#1f2937" } },
      },
    },
  });
}


const PRED_MESSAGES = [
  "Extracting 10 features (RSI, MACD, Bollinger, ATR…)",
  "Training 3-layer LSTM neural network…",
  "Running 100 epochs with early stopping…",
  "Analyzing 60-day price patterns…",
  "Applying gradient clipping & LR scheduling…",
  "Generating 5-day price forecast…",
  "Cross-validating with test set…",
];
let predMsgInterval = null;

async function loadPrediction(ticker, version) {
  const section = document.getElementById("predSection");
  const loader = document.getElementById("predLoader");
  const chartWrap = document.getElementById("predChartWrap");
  const msgEl = document.getElementById("predLoaderMsg");

  section.classList.remove("hidden");
  loader.classList.remove("hidden");
  chartWrap.style.display = "none";

  // Remove any previous retry button
  const oldRetry = document.getElementById("predRetryBtn");
  if (oldRetry) oldRetry.remove();

  let msgIdx = 0;
  msgEl.textContent = PRED_MESSAGES[0];
  predMsgInterval = setInterval(() => {
    msgIdx = (msgIdx + 1) % PRED_MESSAGES.length;
    msgEl.textContent = PRED_MESSAGES[msgIdx];
  }, 3000);

  // 90-second timeout controller
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90000);

  // Show "still working" message after 20s
  const slowWarningId = setTimeout(() => {
    if (msgEl) msgEl.textContent = "⏳ LSTM training in progress — this takes 30–90s on first run…";
  }, 20000);

  try {
    const res = await fetch(`${API}/api/predict/${ticker}`, { signal: controller.signal });
    clearTimeout(timeoutId);
    clearTimeout(slowWarningId);

    if (version !== undefined && version !== loadVersion) {
      clearInterval(predMsgInterval);
      return;
    }
    const data = await res.json();

    if (data.detail) {
      clearInterval(predMsgInterval);
      msgEl.textContent = "⚠️ " + data.detail;
      return;
    }

    clearInterval(predMsgInterval);
    loader.classList.add("hidden");
    chartWrap.style.display = "";

    const confidence = data.confidence != null ? data.confidence : 0;
    const risk = data.risk || "N/A";
    const prices = data.predicted_prices || [];

    document.getElementById("predConf").textContent = confidence + "%";
    document.getElementById("predConf").style.color =
      confidence >= 70 ? "#22c55e" : confidence >= 45 ? "#eab308" : "#ef4444";

    document.getElementById("predRisk").textContent = risk;
    document.getElementById("predRisk").style.color =
      risk === "Low" ? "#22c55e" : risk === "Medium" ? "#eab308" : "#ef4444";

    document.getElementById("predDay1").textContent = prices.length > 0 ? "₹" + prices[0] : "—";
    document.getElementById("predDay5").textContent = prices.length >= 5 ? "₹" + prices[4] : "—";

    if (prices.length > 0 && (data.historical_last_30 || []).length > 0) {
      drawPredictionChart(data);
    }
    renderFactorBreakdown(data);

  } catch (e) {
    clearTimeout(timeoutId);
    clearTimeout(slowWarningId);
    clearInterval(predMsgInterval);

    if (e.name === "AbortError") {
      // Timeout — show retry UI
      msgEl.innerHTML = "⏳ LSTM is still training on the server (can take 2-5 min first time).<br><span style='font-size:11px;color:#859398'>The model will be cached after first run — future loads are instant.</span>";
      const retryBtn = document.createElement("button");
      retryBtn.id = "predRetryBtn";
      retryBtn.textContent = "🔄 Check Again";
      retryBtn.style.cssText = "margin-top:14px;padding:8px 20px;background:rgba(168,232,255,0.1);color:#a8e8ff;border:1px solid rgba(168,232,255,0.3);border-radius:8px;font-size:12px;font-weight:700;cursor:pointer;font-family:inherit";
      retryBtn.onclick = () => { retryBtn.remove(); loadPrediction(ticker, version); };
      loader.querySelector(".pred-loader-inner")?.appendChild(retryBtn);
    } else {
      msgEl.textContent = "⚠️ Forecast failed — " + (e.message || "try again");
    }
  }
}

function renderFactorBreakdown(data) {
  const fb = data.factor_breakdown;
  const container = document.getElementById("factorBreakdown");
  const list = document.getElementById("factorList");
  if (!fb || !container || !list) return;

  container.classList.remove("hidden");
  list.innerHTML = "";

  const factors = [
    { key: "lstm", label: "LSTM Neural", icon: "🧠" },
    { key: "enterprise", label: "Enterprise AI", icon: "🏢" },
    { key: "technical", label: "Technicals", icon: "📈" },
    { key: "sentiment", label: "News Sentiment", icon: "📰" },
    { key: "llm", label: "Gemini LLM", icon: "🤖" },
  ];

  for (const f of factors) {
    const info = fb[f.key];
    if (!info) continue;

    const dir = info.direction || info.contribution || "neutral";
    const weight = info.weight || 0;
    const dirClass = dir === "bullish" || dir === "positive" ? "bullish"
      : dir === "bearish" || dir === "negative" ? "bearish"
        : dir === "shape" ? "shape"
          : dir === "magnitude" ? "magnitude"
            : "neutral";
    const dirLabel = dir === "positive" ? "bullish" : dir === "negative" ? "bearish" : dir;

    const row = document.createElement("div");
    row.className = "factor-row";
    row.innerHTML = `
      <span class="factor-name">${f.icon} ${f.label}</span>
      <div class="factor-bar-wrap">
        <div class="factor-bar-fill ${dirClass}" style="width: 0%"></div>
      </div>
      <span class="factor-weight">${weight}%</span>
      <span class="factor-direction ${dirClass}">${dirLabel}</span>
    `;
    list.appendChild(row);

    // Animate bar width after render
    requestAnimationFrame(() => {
      const bar = row.querySelector(".factor-bar-fill");
      if (bar) bar.style.width = weight + "%";
    });
  }

  // LLM reasoning
  const insight = document.getElementById("llmInsight");
  const textEl = document.getElementById("llmReasoningText");
  if (data.llm_reasoning && insight && textEl) {
    insight.classList.remove("hidden");
    textEl.textContent = `"${data.llm_reasoning}"`;
  } else if (insight) {
    insight.classList.add("hidden");
  }
}

function drawPredictionChart(pred) {
  const hist = pred.historical_last_30;
  const future = pred.predicted_prices;
  const confidence = pred.confidence || 50;

  const histDates = pred.historical_dates || [];
  const predDates = pred.prediction_dates || [];

  const labels = [];
  for (let i = 0; i < hist.length; i++) {
    labels.push(histDates[i] || `D-${hist.length - i}`);
  }
  for (let i = 0; i < future.length; i++) {
    labels.push(predDates[i] || `+${i + 1}d`);
  }

  const histData    = [...hist, ...Array(future.length).fill(null)];
  const predData    = [...Array(hist.length - 1).fill(null), hist[hist.length - 1], ...future];

  // Confidence band — uncertainty grows with lower confidence and further into future
  const uncertaintyFactor = (100 - confidence) / 100; // 0=certain, 1=very uncertain
  const bandUpper = [...Array(hist.length).fill(null)];
  const bandLower = [...Array(hist.length).fill(null)];
  // overlap at last historical point
  bandUpper[hist.length - 1] = hist[hist.length - 1];
  bandLower[hist.length - 1] = hist[hist.length - 1];
  for (let i = 0; i < future.length; i++) {
    const spread = future[i] * uncertaintyFactor * 0.018 * (i + 1); // ±1.8% per day scaled by uncertainty
    bandUpper.push(parseFloat((future[i] + spread).toFixed(2)));
    bandLower.push(parseFloat((future[i] - spread).toFixed(2)));
  }

  if (predChart) predChart.destroy();

  predChart = new Chart(document.getElementById("predChart").getContext("2d"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Historical",
          data: histData,
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59,130,246,0.05)",
          fill: true, tension: 0.3, pointRadius: 0, borderWidth: 2,
          order: 3,
        },
        {
          label: "Upper Band",
          data: bandUpper,
          borderColor: "rgba(34,197,94,0.15)",
          backgroundColor: "rgba(34,197,94,0.10)",
          fill: "+1", tension: 0.3, pointRadius: 0, borderWidth: 1,
          borderDash: [2, 4],
          order: 1,
        },
        {
          label: "Lower Band",
          data: bandLower,
          borderColor: "rgba(34,197,94,0.15)",
          backgroundColor: "rgba(34,197,94,0.10)",
          fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1,
          borderDash: [2, 4],
          order: 1,
        },
        {
          label: `Forecast (${confidence}% confidence)`,
          data: predData,
          borderColor: "#22c55e",
          borderDash: [6, 3],
          backgroundColor: "transparent",
          fill: false, tension: 0.3,
          pointRadius: (ctx) => ctx.dataIndex >= hist.length - 1 ? 5 : 0,
          borderWidth: 2.5,
          pointBackgroundColor: "#22c55e",
          pointBorderColor: "#0f1117",
          pointBorderWidth: 1.5,
          order: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: {
            color: "#6b7280",
            filter: (item) => !item.text.includes("Band"), // hide band labels
          },
        },
        tooltip: {
          backgroundColor: "#0f1117",
          borderColor: "rgba(34,197,94,0.3)",
          borderWidth: 1,
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.label.includes("Band")) return null;
              const val = ctx.raw;
              if (val === null) return null;
              return `${ctx.dataset.label}: ₹${Number(val).toLocaleString("en-IN")}`;
            },
            afterBody: (items) => {
              const idx = items[0]?.dataIndex;
              if (idx !== undefined && idx >= hist.length) {
                const forecastDay = idx - hist.length + 1;
                const upper = bandUpper[idx];
                const lower = bandLower[idx];
                if (upper && lower) {
                  return [`Range: ₹${Number(lower).toLocaleString("en-IN")} – ₹${Number(upper).toLocaleString("en-IN")}`, `Confidence: ${confidence}%`];
                }
              }
              return [];
            },
          },
        },
        annotation: undefined,
      },
      scales: {
        x: { ticks: { color: "#4b5563", maxTicksLimit: 10, maxRotation: 45, font: { size: 9 } }, grid: { color: "rgba(31,41,55,0.6)" } },
        y: {
          ticks: { color: "#4b5563", font: { size: 10 }, callback: (v) => "₹" + Number(v).toLocaleString("en-IN") },
          grid: { color: "rgba(31,41,55,0.6)" }
        },
      },
    },
  });
}


async function loadSentimentAndIndicators(ticker, version) {

  try {
    const sentRes = await fetch(`${API}/api/sentiment/${ticker}`);
    if (version !== undefined && version !== loadVersion) return;
    const sent = await sentRes.json();

    const sentPanel = document.getElementById("sentPanel");
    sentPanel.classList.remove("hidden");

    const gauge = document.getElementById("gaugeCircle");
    gauge.className = `gauge-circle ${sent.overall_sentiment}`;
    document.getElementById("gaugeText").textContent =
      typeof sent.overall_score === "number" ? sent.overall_score.toFixed(2) : sent.overall_score;
    document.getElementById("gaugeLabel").textContent = sent.overall_sentiment.toUpperCase();
    document.getElementById("gaugeLabel").style.color =
      sent.overall_sentiment === "positive" ? "#22c55e" :
        sent.overall_sentiment === "negative" ? "#ef4444" : "#eab308";

    const sentList = document.getElementById("sentList");
    sentList.innerHTML = "";
    (sent.details || []).forEach((d) => {
      const li = document.createElement("li");
      const cls = d.label === "positive" ? "s-pos" : d.label === "negative" ? "s-neg" : "s-neu";
      const score = d.combined_score !== undefined ? ` (${d.combined_score.toFixed(3)})` : "";
      li.innerHTML = `<span class="${cls}">● ${d.label}${score}</span> ${d.text}`;
      sentList.appendChild(li);
    });
  } catch (e) {
    console.error("Sentiment error:", e);
  }


  try {
    const infoRes = await fetch(`${API}/api/summary/${ticker}`);
    if (version !== undefined && version !== loadVersion) return;
    const data = await infoRes.json();

    if (data.indicators) {
      const indPanel = document.getElementById("indPanel");
      indPanel.classList.remove("hidden");
      const indBody = document.getElementById("indBody");
      indBody.innerHTML = "";
      Object.entries(data.indicators).forEach(([key, val]) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${key}</td><td>${val}</td>`;
        indBody.appendChild(tr);
      });
    }
  } catch (e) {
    console.error("Indicators error:", e);
  }
}


async function loadHighPotential() {
  try {
    const res = await fetch(`${API}/api/high-potential`);
    const data = await res.json();

    document.getElementById("hpLoader").classList.add("hidden");
    const list = document.getElementById("hpList");
    list.innerHTML = "";

    data.stocks.forEach((s) => {
      const div = document.createElement("div");
      div.className = "hp-item";
      div.onclick = () => {
        document.getElementById("tickerInput").value = s.ticker;
        loadTicker(s.ticker);
      };

      const changeClass = s.change_pct >= 0 ? "up" : "down";
      const sign = s.change_pct >= 0 ? "+" : "";
      const scoreClass = s.score >= 70 ? "high" : s.score >= 45 ? "med" : "low";

      div.innerHTML = `
        <div>
          <div class="hp-ticker">${s.ticker}</div>
          <div class="hp-name">${s.name}</div>
        </div>
        <div>
          <div class="hp-price">₹${s.price}</div>
          <div class="hp-change ${changeClass}">${sign}${s.change_pct}%</div>
        </div>
        <div class="hp-score ${scoreClass}">${s.signal}</div>
      `;
      list.appendChild(div);
    });
  } catch (e) {
    document.getElementById("hpLoader").textContent = "⚠️ Scanner unavailable";
    console.error("High potential error:", e);
  }
}


async function loadPortfolio() {
  try {
    const res = await fetch(`${API}/api/trade/portfolio`);
    const data = await res.json();


    document.getElementById("portValue").textContent = "₹" + formatNumber(data.total_value || data.balance);
    document.getElementById("portBalance").textContent = "₹" + formatNumber(data.balance);

    const unrealized = data.total_unrealized_pnl || 0;
    const unrealizedEl = document.getElementById("portUnrealized");
    unrealizedEl.textContent = (unrealized >= 0 ? "+₹" : "-₹") + formatNumber(Math.abs(unrealized));
    unrealizedEl.style.color = unrealized >= 0 ? "#22c55e" : "#ef4444";

    const realized = data.total_realized_pnl || 0;
    const realizedEl = document.getElementById("portRealized");
    realizedEl.textContent = (realized >= 0 ? "+₹" : "-₹") + formatNumber(Math.abs(realized));
    realizedEl.style.color = realized >= 0 ? "#22c55e" : "#ef4444";

    document.getElementById("portWinRate").textContent = (data.win_rate || 0) + "%";
    document.getElementById("portWinRate").style.color = data.win_rate >= 50 ? "#22c55e" : "#ef4444";

    document.getElementById("portTrades").textContent = data.total_trades || 0;


    const botDot = document.getElementById("botDot");
    const botStatus = document.getElementById("botStatus");
    const toggleBtn = document.getElementById("toggleBotBtn");

    if (data.bot_active) {
      botDot.className = "bot-dot active";
      botStatus.textContent = "Bot: ACTIVE";
      botStatus.style.color = "#22c55e";
      toggleBtn.textContent = "⏹ Deactivate Bot";
      toggleBtn.classList.add("active");
    } else {
      botDot.className = "bot-dot";
      botStatus.textContent = "Bot: OFF";
      botStatus.style.color = "#ef4444";
      toggleBtn.textContent = "⚡ Activate Bot";
      toggleBtn.classList.remove("active");
    }


    renderPositions(data.positions || {});


    renderTradeHistory(data.trade_history || []);

  } catch (e) {
    console.error("Portfolio error:", e);
  }
}


function renderPositions(positions) {
  const tbody = document.getElementById("positionsBody");

  if (Object.keys(positions).length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="empty-msg">No open positions — activate the bot or trade manually</td></tr>';
    return;
  }

  tbody.innerHTML = "";
  Object.entries(positions).forEach(([ticker, pos]) => {
    const pnl = pos.unrealized_pnl || 0;
    const pnlPct = pos.pnl_pct || 0;
    const pnlClass = pnl >= 0 ? "pnl-positive" : "pnl-negative";
    const pnlSign = pnl >= 0 ? "+" : "";
    const sl = pos.stop_loss || 0;
    const tp = pos.tp1 || pos.take_profit || 0;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="ticker-col">${ticker}</td>
      <td>${pos.shares}</td>
      <td>₹${pos.buy_price}</td>
      <td>₹${pos.current_price || pos.buy_price}</td>
      <td class="${pnlClass}">${pnlSign}₹${formatNumber(Math.abs(pnl))}</td>
      <td class="${pnlClass}">${pnlSign}${pnlPct}%</td>
      <td style="color:#ef4444">₹${sl}</td>
      <td style="color:#22c55e">₹${tp}</td>
      <td><button class="btn-sell-small" onclick="forceSell('${ticker}')">SELL</button></td>
    `;
    tbody.appendChild(tr);
  });
}


function renderTradeHistory(trades) {
  const log = document.getElementById("tradeLog");

  if (trades.length === 0) {
    log.innerHTML = '<div class="empty-msg">No trades yet. Activate the bot or execute a trade.</div>';
    return;
  }

  log.innerHTML = "";

  [...trades].reverse().forEach((t) => {
    const profit = (typeof t.profit === "number" && !isNaN(t.profit)) ? t.profit : 0;
    const profit_pct = (typeof t.profit_pct === "number" && !isNaN(t.profit_pct)) ? t.profit_pct : 0;
    const profitClass = profit >= 0 ? "pnl-positive" : "pnl-negative";
    const profitSign = profit >= 0 ? "+" : "";
    const time = new Date(t.sell_time).toLocaleString();

    const entry = document.createElement("div");
    entry.className = "trade-entry";
    entry.innerHTML = `
      <span class="te-time">${time}</span>
      <span>
        <span class="te-ticker">${t.ticker}</span>
        — ${t.shares} shares @ ₹${t.buy_price} → ₹${t.sell_price}
        <span style="color:#6b7280;font-size:0.7rem;"> (${t.reason})</span>
      </span>
      <span class="${profitClass}">${profitSign}₹${formatNumber(Math.abs(profit))}</span>
      <span class="${profitClass}">${profitSign}${profit_pct}%</span>
    `;
    log.appendChild(entry);
  });
}


function addToFeed(message, type) {
  const feed = document.getElementById("tradeFeed");
  const time = new Date().toLocaleTimeString();

  const item = document.createElement("div");
  item.className = `feed-item ${type}`;
  item.innerHTML = `<span style="color:#6b7280;font-size:0.7rem;">[${time}]</span> ${message}`;


  feed.insertBefore(item, feed.firstChild);


  while (feed.children.length > 50) {
    feed.removeChild(feed.lastChild);
  }
}


async function toggleBot() {
  try {
    const res = await fetch(`${API}/api/trade/toggle`, { method: "POST" });
    const data = await res.json();

    if (data.bot_active) {
      addToFeed("🤖 <strong>Auto-trading bot ACTIVATED</strong> — scanning for opportunities...", "buy");
    } else {
      addToFeed("⏹ <strong>Auto-trading bot DEACTIVATED</strong>", "sell");
    }

    loadPortfolio();
  } catch (e) {
    console.error("Toggle error:", e);
    addToFeed("❌ Failed to toggle bot", "sell");
  }
}


async function executeManualTrade() {
  const ticker = currentTicker || document.getElementById("tickerInput").value.trim().toUpperCase();
  if (!ticker) {
    alert("Enter a ticker first!");
    return;
  }

  addToFeed(`🔄 Analyzing <strong>${ticker}</strong> — running LSTM + Technical + Sentiment...`, "hold");

  try {
    const res = await fetch(`${API}/api/trade/execute/${ticker}`, { method: "POST" });
    const data = await res.json();

    const action = data.action;
    const price = data.current_price;

    if (action === "BUY") {
      const tr = data.trade_result;
      const cs = data.composite_score || '?';
      const regime = data.market_regime || 'NEUTRAL';
      const regimeIcon = regime === 'BULL' ? '🐂' : regime === 'BEAR' ? '🐻' : '⚖️';
      addToFeed(
        `🟢 <strong>BOUGHT ${tr.shares} x ${ticker}</strong> @ ₹${price} | ` +
        `${regimeIcon} ${regime} | Score: ${cs}/100 | SL: ₹${tr.stop_loss} | TP: ₹${tr.tp1}`,
        "buy"
      );
    } else if (action === "SELL") {
      const tr = data.trade_result;
      const profit = (typeof tr.profit === "number" && !isNaN(tr.profit)) ? tr.profit : 0;
      const profit_pct = (typeof tr.profit_pct === "number" && !isNaN(tr.profit_pct)) ? tr.profit_pct : 0;
      const profitSign = profit >= 0 ? "+" : "";
      addToFeed(
        `🔴 <strong>SOLD ${ticker}</strong> @ ₹${price} | ` +
        `P&L: ${profitSign}₹${profit} (${profitSign}${profit_pct}%) | Reason: ${tr.reason}`,
        "sell"
      );
    } else if (action === "HOLD") {
      addToFeed(
        `🟡 <strong>HOLD ${ticker}</strong> @ ₹${price} — position within thresholds ` +
        `(P&L: ${data.position.current_pnl}%)`,
        "hold"
      );
    } else {
      const cs = data.composite_score || '?';
      const regime = data.market_regime || 'NEUTRAL';
      const regimeIcon = regime === 'BULL' ? '🐂' : regime === 'BEAR' ? '🐻' : '⚖️';
      addToFeed(
        `⚪ <strong>WAIT on ${ticker}</strong> @ ₹${price} — ${regimeIcon} ${regime} | Score: ${cs}/100 | ` +
        `${data.reason || "conditions not met"}`,
        "wait"
      );
    }

    loadPortfolio();
  } catch (e) {
    console.error("Trade error:", e);
    addToFeed(`❌ Trade execution failed for ${ticker}: ${e.message}`, "sell");
  }
}


async function runAutoScan() {
  addToFeed("🔍 <strong>Auto-scan started</strong> — XGBoost intraday analysis with regime detection...", "hold");

  try {
    const res = await fetch(`${API}/api/trade/auto-scan`, { method: "POST" });
    const data = await res.json();

    if (data.status === "inactive") {
      addToFeed("⚠️ Bot is OFF — activate it first before scanning", "wait");
      return;
    }

    addToFeed(`✅ <strong>Scan complete</strong> — analyzed ${data.scanned} stocks`, "hold");


    (data.results || []).forEach((r) => {
      const action = r.action;
      const ticker = r.ticker;

      if (action === "BUY" && r.trade_result) {
        const tr = r.trade_result;
        if (tr.status === "bought") {
          addToFeed(
            `🟢 <strong>AUTO-BUY ${tr.shares} x ${ticker}</strong> @ ₹${tr.price} | ` +
            `SL: ₹${tr.stop_loss || 0} | TP: ₹${tr.tp1 || 0}`,
            "buy"
          );
        } else {
          addToFeed(`⚪ ${ticker}: ${tr.reason || "skipped"}`, "wait");
        }
      } else if (action === "SELL" && (r.trade_result || r.result)) {
        const tr = r.trade_result || r.result;
        const profit = (typeof tr.profit === "number" && !isNaN(tr.profit)) ? tr.profit : 0;
        const profitSign = profit >= 0 ? "+" : "";
        addToFeed(
          `🔴 <strong>AUTO-SELL ${ticker}</strong> | P&L: ${profitSign}₹${profit} | ${tr.reason || ''}`,
          "sell"
        );
      } else if (action === "WAIT") {
        const regime = r.regime || 'SIDEWAYS';
        const conf = r.confidence || 0;
        const expRet = r.expected_return_pct || 0;
        const regimeIcon = regime.includes('BULL') ? '🐂' : regime.includes('BEAR') ? '🐻' : '⚖️';
        addToFeed(
          `⚪ ${ticker}: WAIT — ${regimeIcon} ${regime} | Confidence: ${conf} | Expected: ${expRet}%`,
          "wait"
        );
      } else if (action === "SKIP") {
        addToFeed(`⚪ ${ticker}: SKIP — ${r.reason || 'insufficient data'}`, "wait");
      }
    });

    loadPortfolio();
  } catch (e) {
    console.error("Scan error:", e);
    addToFeed(`❌ Auto-scan failed: ${e.message}`, "sell");
  }
}


async function forceSell(ticker) {
  if (!confirm(`Force sell all ${ticker} shares at market price?`)) return;

  addToFeed(`🔄 Force-selling <strong>${ticker}</strong>...`, "hold");

  try {
    const res = await fetch(`${API}/api/trade/sell/${ticker}`, { method: "POST" });
    const data = await res.json();

    if (data.status === "sold") {
      const profitSign = data.profit >= 0 ? "+" : "";
      addToFeed(
        `🔴 <strong>FORCE-SOLD ${ticker}</strong> @ ₹${data.price} | ` +
        `P&L: ${profitSign}₹${data.profit} (${profitSign}${data.profit_pct}%)`,
        "sell"
      );
    } else {
      addToFeed(`⚠️ ${ticker}: ${data.reason}`, "wait");
    }

    loadPortfolio();
  } catch (e) {
    console.error("Force sell error:", e);
    addToFeed(`❌ Force sell failed: ${e.message}`, "sell");
  }
}


async function resetPortfolio() {
  if (!confirm("Reset portfolio to ₹10,00,000? All positions and history will be lost.")) return;

  try {
    await fetch(`${API}/api/trade/reset`, { method: "POST" });
    addToFeed("🔄 <strong>Portfolio reset</strong> to ₹10,00,000.00", "hold");
    loadPortfolio();
  } catch (e) {
    console.error("Reset error:", e);
  }
}


function formatPrice(p) {
  if (!p) return "—";
  return parseFloat(p).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatVolume(v) {
  if (!v) return "—";
  if (v >= 1e9) return (v / 1e9).toFixed(2) + "B";
  if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
  if (v >= 1e3) return (v / 1e3).toFixed(1) + "K";
  return v.toString();
}

function formatNumber(n) {
  return parseFloat(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}


// ============================================================================
// TRADE PANEL
// ============================================================================

let tradePanelTicker = "";
let tradePanelPrice = 0;
let tradePanelAction = "buy"; // "buy" or "sell"
let tradePanelInterval = null;
let accountValueChart = null;
let watchlistRefreshInterval = null;

function openTradePanel(ticker) {
  const panel = document.getElementById("tradePanel");
  panel.classList.remove("hidden");
  document.body.style.overflow = "hidden";

  // Set up trade search
  const searchInput = document.getElementById("tradeSearchInput");
  searchInput.value = "";
  document.getElementById("tradeSearchDropdown").classList.add("hidden");

  // Update market badge
  updateTradePanelMarketBadge();

  // Update wallet balance in summary
  document.getElementById("tpSummaryBalance").textContent = "₹" + formatNumber(walletBalance);

  if (ticker) {
    selectTradeStock(ticker);
    searchInput.value = ticker;
  } else {
    document.getElementById("tpStockCard").classList.add("hidden");
  }

  // Setup search listeners
  setupTradePanelSearch();

  // Load holdings, history, watchlist
  loadTradeHoldings();
  loadTradeHistory();
  renderWatchlist();

  // Start watchlist price refresh
  if (watchlistRefreshInterval) clearInterval(watchlistRefreshInterval);
  watchlistRefreshInterval = setInterval(refreshWatchlistPrices, 15000);
}

function closeTradePanel() {
  document.getElementById("tradePanel").classList.add("hidden");
  document.body.style.overflow = "";
  if (tradePanelInterval) {
    clearInterval(tradePanelInterval);
    tradePanelInterval = null;
  }
  if (watchlistRefreshInterval) {
    clearInterval(watchlistRefreshInterval);
    watchlistRefreshInterval = null;
  }
}

function switchTradeTab(tab) {
  document.querySelectorAll(".tp-tab").forEach(t => t.classList.remove("active"));
  document.querySelector(`.tp-tab[data-tab="${tab}"]`).classList.add("active");

  document.querySelectorAll(".tp-tab-content").forEach(c => c.classList.add("hidden"));

  if (tab === "search") {
    document.getElementById("tpSearchTab").classList.remove("hidden");
  } else if (tab === "holdings") {
    document.getElementById("tpHoldingsTab").classList.remove("hidden");
    loadTradeHoldings();
  } else if (tab === "history") {
    document.getElementById("tpHistoryTab").classList.remove("hidden");
    loadTradeHistory();
  } else if (tab === "watchlist") {
    document.getElementById("tpWatchlistTab").classList.remove("hidden");
    renderWatchlist();
    refreshWatchlistPrices();
  }
}

let tradeSearchTimeout = null;
function setupTradePanelSearch() {
  const input = document.getElementById("tradeSearchInput");
  const dropdown = document.getElementById("tradeSearchDropdown");

  // Remove old listeners by cloning
  const newInput = input.cloneNode(true);
  input.parentNode.replaceChild(newInput, input);

  newInput.addEventListener("input", () => {
    clearTimeout(tradeSearchTimeout);
    const q = newInput.value.trim();
    if (q.length < 1) {
      dropdown.classList.add("hidden");
      return;
    }
    tradeSearchTimeout = setTimeout(() => tradeSearchStocks(q), 250);
  });

  newInput.addEventListener("keydown", (e) => {
    if (e.key === "Escape") dropdown.classList.add("hidden");
  });
}

async function tradeSearchStocks(query) {
  const dropdown = document.getElementById("tradeSearchDropdown");
  try {
    const res = await fetch(`${API}/api/search?q=${encodeURIComponent(query)}`);
    const data = await res.json();

    if (!data.results || data.results.length === 0) {
      dropdown.innerHTML = '<div class="tp-search-no-results">No stocks found</div>';
      dropdown.classList.remove("hidden");
      return;
    }

    dropdown.innerHTML = data.results.map(s => `
      <div class="tp-search-item" data-ticker="${s.ticker}" data-name="${s.name}">
        <span class="tp-search-ticker">${s.ticker}</span>
        <span class="tp-search-name">${s.name}</span>
      </div>
    `).join("");

    dropdown.querySelectorAll(".tp-search-item").forEach(item => {
      item.addEventListener("click", () => {
        const ticker = item.dataset.ticker;
        document.getElementById("tradeSearchInput").value = ticker;
        dropdown.classList.add("hidden");
        selectTradeStock(ticker);
      });
    });

    dropdown.classList.remove("hidden");
  } catch (e) {
    console.error("Trade search error:", e);
    dropdown.classList.add("hidden");
  }
}

async function selectTradeStock(ticker) {
  tradePanelTicker = ticker;
  const card = document.getElementById("tpStockCard");
  card.classList.remove("hidden");

  document.getElementById("tpStockTicker").textContent = ticker;
  document.getElementById("tpStockName").textContent = ticker;
  document.getElementById("tpStockPrice").textContent = "Loading...";
  document.getElementById("tpStockChange").textContent = "";

  // Check if in watchlist
  updateWatchlistButton(ticker);

  // Fetch live price
  await updateTradePanelPrice(ticker);

  // Auto-refresh price every 10s
  if (tradePanelInterval) clearInterval(tradePanelInterval);
  tradePanelInterval = setInterval(() => updateTradePanelPrice(ticker), 10000);

  // Also fetch stock info for name
  try {
    const infoRes = await fetch(`${API}/api/stock/${ticker}`);
    const infoData = await infoRes.json();
    if (infoData.info && infoData.info.name) {
      document.getElementById("tpStockName").textContent = infoData.info.name;
    }
  } catch (e) { /* ignore */ }

  // Check if position exists to default to sell
  try {
    const portRes = await fetch(`${API}/api/trade/portfolio`);
    const portData = await portRes.json();
    if (portData.positions && portData.positions[ticker]) {
      setTradeAction("sell");
    } else {
      setTradeAction("buy");
    }
  } catch (e) { /* ignore */ }
}

async function updateTradePanelPrice(ticker) {
  try {
    const res = await fetch(`${API}/api/live/${ticker}`);
    const data = await res.json();
    tradePanelPrice = data.price;

    document.getElementById("tpStockPrice").textContent = "₹" + formatPrice(data.price);
    const sign = data.change >= 0 ? "+" : "";
    const changeEl = document.getElementById("tpStockChange");
    changeEl.textContent = `${sign}${data.change} (${sign}${data.change_pct}%)`;
    changeEl.className = `tp-stock-change ${data.direction}`;

    document.getElementById("tpSummaryPrice").textContent = "₹" + formatPrice(data.price);
    updateOrderSummary();
  } catch (e) {
    console.error("Trade panel price error:", e);
  }
}

function setTradeAction(action) {
  tradePanelAction = action;
  const buyBtn = document.getElementById("tpBuyBtn");
  const sellBtn = document.getElementById("tpSellBtn");
  const execBtn = document.getElementById("tpExecuteBtn");

  if (action === "buy") {
    buyBtn.classList.add("active");
    buyBtn.classList.remove("sell");
    sellBtn.classList.remove("active");
    execBtn.textContent = "⚡ Place BUY Order";
    execBtn.className = "tp-execute-btn buy";
  } else {
    sellBtn.classList.add("active");
    buyBtn.classList.remove("active");
    execBtn.textContent = "⚡ Place SELL Order";
    execBtn.className = "tp-execute-btn sell-mode";
  }
}

function updateOrderSummary() {
  const qty = parseInt(document.getElementById("tpQuantity").value) || 1;
  const total = qty * tradePanelPrice;
  document.getElementById("tpSummaryQty").textContent = qty;
  document.getElementById("tpSummaryTotal").textContent = "₹" + formatNumber(total);
  document.getElementById("tpSummaryBalance").textContent = "₹" + formatNumber(walletBalance);
}

// Attach qty input listener
document.addEventListener("DOMContentLoaded", () => {
  // Delayed to ensure element exists
  setTimeout(() => {
    const qtyInput = document.getElementById("tpQuantity");
    if (qtyInput) {
      qtyInput.addEventListener("input", updateOrderSummary);
    }
  }, 500);
});


async function executeTradeFromPanel() {
  if (!tradePanelTicker) {
    alert("Select a stock first!");
    return;
  }

  const btn = document.getElementById("tpExecuteBtn");
  const origText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Processing...";

  try {
    if (tradePanelAction === "buy") {
      // Execute buy via the AI trade endpoint
      const res = await fetch(`${API}/api/trade/execute/${tradePanelTicker}`, { method: "POST" });
      const data = await res.json();

      if (data.action === "BUY" && data.trade_result) {
        const tr = data.trade_result;
        alert(`✅ Bought ${tr.shares} shares of ${tradePanelTicker} @ ₹${data.current_price}\nSL: ₹${tr.stop_loss} | TP: ₹${tr.tp1}`);
        addToFeed(`🟢 <strong>BOUGHT ${tr.shares} x ${tradePanelTicker}</strong> @ ₹${data.current_price}`, "buy");
      } else if (data.action === "WAIT") {
        alert(`⏸ AI recommends WAIT for ${tradePanelTicker}.\nReason: ${data.reason || "Conditions not met"}`);
      } else if (data.action === "HOLD") {
        alert(`📊 Already holding ${tradePanelTicker}. AI says HOLD.`);
      } else if (data.action === "SELL" && data.trade_result) {
        const tr = data.trade_result;
        alert(`🔴 AI triggered SELL for ${tradePanelTicker}\nP&L: ₹${tr.profit} (${tr.profit_pct}%)`);
        addToFeed(`🔴 <strong>SOLD ${tradePanelTicker}</strong> | P&L: ₹${tr.profit}`, "sell");
      }
    } else {
      // Execute sell
      const res = await fetch(`${API}/api/trade/sell/${tradePanelTicker}`, { method: "POST" });
      const data = await res.json();

      if (data.status === "sold") {
        const profitSign = data.profit >= 0 ? "+" : "";
        alert(`✅ Sold ${tradePanelTicker} @ ₹${data.price}\nP&L: ${profitSign}₹${data.profit} (${profitSign}${data.profit_pct}%)`);
        addToFeed(`🔴 <strong>SOLD ${tradePanelTicker}</strong> @ ₹${data.price} | P&L: ${profitSign}₹${data.profit}`, "sell");
      } else {
        alert(`⚠️ ${data.reason || "Could not sell"}`);
      }
    }

    // Reload
    loadPortfolio();
    loadWalletBalance();
    loadTradeHoldings();
    loadTradeHistory();
    updateOrderSummary();

  } catch (e) {
    console.error("Trade execution error:", e);
    alert(`❌ Trade failed: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = origText;
  }
}


// ── Holdings Tab ────────────────────────────────────────

async function loadTradeHoldings() {
  const list = document.getElementById("tpHoldingsList");
  try {
    const res = await fetch(`${API}/api/trade/portfolio`);
    const data = await res.json();
    const positions = data.positions || {};

    if (Object.keys(positions).length === 0) {
      list.innerHTML = '<div class="tp-empty">No holdings. Start trading to see your positions here.</div>';
      return;
    }

    list.innerHTML = Object.entries(positions).map(([ticker, pos]) => {
      const pnl = pos.unrealized_pnl || 0;
      const pnlPct = pos.pnl_pct || 0;
      const pnlClass = pnl >= 0 ? "positive" : "negative";
      const pnlSign = pnl >= 0 ? "+" : "";
      const currentPrice = pos.current_price || pos.buy_price;

      return `
        <div class="tp-holding-card">
          <div class="tp-holding-main">
            <div class="tp-holding-left">
              <span class="tp-holding-ticker">${ticker}</span>
              <span class="tp-holding-shares">${pos.shares} shares @ ₹${pos.buy_price}</span>
            </div>
            <div class="tp-holding-right">
              <span class="tp-holding-price">₹${formatPrice(currentPrice)}</span>
              <span class="tp-holding-pnl ${pnlClass}">${pnlSign}₹${formatNumber(Math.abs(pnl))} (${pnlSign}${pnlPct}%)</span>
            </div>
          </div>
          <div class="tp-holding-actions">
            <button class="tp-holding-trade-btn" onclick="selectTradeStock('${ticker}'); switchTradeTab('search');">Trade</button>
            <button class="tp-holding-sell-btn" onclick="forceSellFromPanel('${ticker}')">Quick Sell</button>
          </div>
        </div>
      `;
    }).join("");

  } catch (e) {
    console.error("Holdings load error:", e);
    list.innerHTML = '<div class="tp-empty">Error loading holdings</div>';
  }
}

async function forceSellFromPanel(ticker) {
  if (!confirm(`Sell all ${ticker} shares at market price?`)) return;
  try {
    const res = await fetch(`${API}/api/trade/sell/${ticker}`, { method: "POST" });
    const data = await res.json();
    if (data.status === "sold") {
      const profitSign = data.profit >= 0 ? "+" : "";
      alert(`✅ Sold ${ticker} @ ₹${data.price}\nP&L: ${profitSign}₹${data.profit}`);
      addToFeed(`🔴 <strong>SOLD ${ticker}</strong> @ ₹${data.price}`, "sell");
    } else {
      alert(data.reason || "Could not sell");
    }
    loadTradeHoldings();
    loadPortfolio();
    loadWalletBalance();
  } catch (e) {
    alert(`Error: ${e.message}`);
  }
}


// ── History Tab ─────────────────────────────────────────

async function loadTradeHistory() {
  const list = document.getElementById("tpHistoryList");
  try {
    const res = await fetch(`${API}/api/trade/portfolio`);
    const data = await res.json();
    const trades = data.trade_history || [];

    if (trades.length === 0) {
      list.innerHTML = '<div class="tp-empty">No trade history yet. Complete a trade to see it here.</div>';
      return;
    }

    list.innerHTML = [...trades].reverse().map(t => {
      const profit = (typeof t.profit === "number" && !isNaN(t.profit)) ? t.profit : 0;
      const profitPct = (typeof t.profit_pct === "number" && !isNaN(t.profit_pct)) ? t.profit_pct : 0;
      const profitClass = profit >= 0 ? "positive" : "negative";
      const profitSign = profit >= 0 ? "+" : "";
      const time = new Date(t.sell_time).toLocaleString("en-IN");

      return `
        <div class="tp-history-card">
          <div class="tp-history-main">
            <div class="tp-history-left">
              <span class="tp-history-ticker">${t.ticker}</span>
              <span class="tp-history-details">${t.shares} shares @ ₹${t.buy_price} → ₹${t.sell_price}</span>
              <span class="tp-history-time">${time}</span>
            </div>
            <div class="tp-history-right">
              <span class="tp-history-pnl ${profitClass}">${profitSign}₹${formatNumber(Math.abs(profit))}</span>
              <span class="tp-history-pnl-pct ${profitClass}">${profitSign}${profitPct}%</span>
            </div>
          </div>
          <span class="tp-history-reason">${t.reason || ""}</span>
        </div>
      `;
    }).join("");

  } catch (e) {
    console.error("History load error:", e);
    list.innerHTML = '<div class="tp-empty">Error loading trade history</div>';
  }
}


// ── Watchlist ───────────────────────────────────────────

function getWatchlist() {
  try {
    return JSON.parse(localStorage.getItem("stocksense_watchlist") || "[]");
  } catch (e) { return []; }
}

function saveWatchlist(wl) {
  localStorage.setItem("stocksense_watchlist", JSON.stringify(wl));
}

function addToWatchlist(ticker) {
  const wl = getWatchlist();
  if (!wl.includes(ticker)) {
    wl.push(ticker);
    saveWatchlist(wl);
  }
}

function removeFromWatchlist(ticker) {
  let wl = getWatchlist();
  wl = wl.filter(t => t !== ticker);
  saveWatchlist(wl);
  renderWatchlist();
}

function toggleWatchlistFromPanel() {
  if (!tradePanelTicker) return;
  const wl = getWatchlist();
  if (wl.includes(tradePanelTicker)) {
    removeFromWatchlist(tradePanelTicker);
  } else {
    addToWatchlist(tradePanelTicker);
  }
  updateWatchlistButton(tradePanelTicker);
  renderWatchlist();
}

function updateWatchlistButton(ticker) {
  const btn = document.getElementById("tpWatchlistBtn");
  const wl = getWatchlist();
  if (wl.includes(ticker)) {
    btn.textContent = "⭐ Remove from Watchlist";
    btn.classList.add("in-watchlist");
  } else {
    btn.textContent = "☆ Add to Watchlist";
    btn.classList.remove("in-watchlist");
  }
}

function renderWatchlist() {
  const list = document.getElementById("tpWatchlistList");
  const wl = getWatchlist();

  if (wl.length === 0) {
    list.innerHTML = '<div class="tp-empty">Your watchlist is empty. Search for a stock and click ⭐ to add.</div>';
    return;
  }

  list.innerHTML = wl.map(ticker => `
    <div class="tp-watchlist-item" id="wl-${ticker.replace('.', '-')}">
      <div class="tp-wl-left" onclick="selectTradeStock('${ticker}'); switchTradeTab('search');" style="cursor:pointer;">
        <span class="tp-wl-ticker">${ticker}</span>
        <span class="tp-wl-price" id="wlPrice-${ticker.replace('.', '-')}">—</span>
      </div>
      <div class="tp-wl-right">
        <span class="tp-wl-change" id="wlChange-${ticker.replace('.', '-')}">—</span>
        <button class="tp-wl-remove" onclick="removeFromWatchlist('${ticker}')" title="Remove">✕</button>
      </div>
    </div>
  `).join("");
}

async function refreshWatchlistPrices() {
  const wl = getWatchlist();
  for (const ticker of wl) {
    try {
      const res = await fetch(`${API}/api/live/${ticker}`);
      const data = await res.json();
      const safeId = ticker.replace('.', '-');
      const priceEl = document.getElementById(`wlPrice-${safeId}`);
      const changeEl = document.getElementById(`wlChange-${safeId}`);
      if (priceEl) priceEl.textContent = "₹" + formatPrice(data.price);
      if (changeEl) {
        const sign = data.change >= 0 ? "+" : "";
        changeEl.textContent = `${sign}${data.change_pct}%`;
        changeEl.className = `tp-wl-change ${data.direction}`;
      }
    } catch (e) { /* ignore */ }
  }
}


// ── Market Hours Detection (IST) ────────────────────────

function isIndianMarketOpen() {
  const now = new Date();
  // Convert to IST (UTC+5:30)
  const utc = now.getTime() + now.getTimezoneOffset() * 60000;
  const ist = new Date(utc + 5.5 * 3600000);

  const day = ist.getDay(); // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false;

  const hours = ist.getHours();
  const minutes = ist.getMinutes();
  const timeMinutes = hours * 60 + minutes;

  // 9:15 AM to 3:30 PM IST
  return timeMinutes >= 555 && timeMinutes <= 930;
}

function updateTradePanelMarketBadge() {
  const live = isIndianMarketOpen();
  const badge = document.getElementById("tpMarketBadge");
  const status = document.getElementById("tpMarketStatus");
  const dot = badge ? badge.querySelector(".dot") : null;

  if (status) status.textContent = live ? "MARKET OPEN" : "MARKET CLOSED";
  if (dot) {
    dot.style.background = live ? "#22c55e" : "#6b7280";
    dot.style.animation = live ? "pulse 1.5s infinite" : "none";
  }
  if (badge) badge.className = `tp-market-badge ${live ? "live" : "offline"}`;
}


// ── Account Value Chart ─────────────────────────────────

async function drawAccountValueChart() {
  try {
    const res = await fetch(`${API}/api/portfolio/value-history`);
    const data = await res.json();
    const snapshots = data.snapshots || [];

    if (snapshots.length === 0) return;

    // Also add current value
    try {
      const portRes = await fetch(`${API}/api/trade/portfolio`);
      const portData = await portRes.json();
      const currentVal = portData.total_value || portData.balance;
      snapshots.push({
        timestamp: new Date().toISOString(),
        value: currentVal,
      });
    } catch (e) { /* ignore */ }

    const labels = snapshots.map(s => {
      const d = new Date(s.timestamp);
      return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" }) + " " +
        d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
    });
    const values = snapshots.map(s => s.value);

    const isUp = values[values.length - 1] >= values[0];
    const lineColor = isUp ? "#22c55e" : "#ef4444";
    const fillColor = isUp ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)";

    if (accountValueChart) accountValueChart.destroy();

    const ctx = document.getElementById("accountValueChart");
    if (!ctx) return;

    accountValueChart = new Chart(ctx.getContext("2d"), {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Account Value",
          data: values,
          borderColor: lineColor,
          backgroundColor: fillColor,
          fill: true,
          tension: 0.4,
          pointRadius: values.length > 20 ? 0 : 3,
          borderWidth: 2,
          pointBackgroundColor: lineColor,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#1a1f2e",
            borderColor: "#242a38",
            borderWidth: 1,
            titleColor: "#fff",
            bodyColor: "#d1d5db",
            callbacks: {
              label: (ctx) => "₹" + formatNumber(ctx.parsed.y),
            },
          },
        },
        scales: {
          x: {
            ticks: { color: "#4b5563", maxTicksLimit: 6, maxRotation: 0, font: { size: 9 } },
            grid: { color: "#1f2937" },
          },
          y: {
            ticks: {
              color: "#4b5563",
              font: { size: 10 },
              callback: (v) => "₹" + (v / 1000).toFixed(0) + "K",
            },
            grid: { color: "#1f2937" },
          },
        },
      },
    });

    // Update market badge on account value section
    updateAccountValueMarketBadge();

  } catch (e) {
    console.error("Account value chart error:", e);
  }
}

function updateAccountValueMarketBadge() {
  const live = isIndianMarketOpen();
  const dot = document.getElementById("avMarketDot");
  const label = document.getElementById("avMarketLabel");
  const badge = document.getElementById("avMarketBadge");

  if (label) label.textContent = live ? "LIVE" : "OFFLINE";
  if (dot) {
    dot.style.background = live ? "#22c55e" : "#6b7280";
    dot.style.animation = live ? "pulse 1.5s infinite" : "none";
  }
  if (badge) badge.className = `av-market-badge ${live ? "live" : "offline"}`;
}

// Load account value chart when switching to trading tab
const origSwitchTab = switchTab;
switchTab = function (tab) {
  origSwitchTab(tab);
  if (tab === "trading") {
    setTimeout(drawAccountValueChart, 300);
  }
};

// Initial market badge update
setInterval(updateAccountValueMarketBadge, 60000);

// Topbar live badge: green during Indian market hours, red when closed
function updateTopbarLiveBadge() {
  const live = isIndianMarketOpen();
  const badge = document.getElementById("liveBadge");
  const textEl = document.getElementById("liveBadgeText");
  const dot = badge ? badge.querySelector(".dot") : null;
  if (textEl) textEl.textContent = live ? "LIVE" : "CLOSED";
  if (badge) {
    badge.classList.remove("live", "closed");
    badge.classList.add(live ? "live" : "closed");
  }
  if (dot) {
    dot.style.background = live ? "#22c55e" : "#ef4444";
    dot.style.animation = live ? "pulse 1.5s infinite" : "none";
  }
}
