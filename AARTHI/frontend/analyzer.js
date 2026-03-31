const API_URL = "http://localhost:8000/analyze";

let literacyScore = 1;
let currentStep   = 1;

// ── Step navigation ───────────────────────────────────────

function showStep(n) {
    currentStep = n;
    [1, 2, 3].forEach(i => {
        document.getElementById("az-step" + i).classList.toggle("visible", i === n);
        document.getElementById("seg" + i).classList.toggle("active", i <= n);
    });
    document.getElementById("az-step-label").textContent = `Step ${n} of 3`;
}

function azNext(from) {
    if (from === 1) {
        const inc = document.getElementById("income").value;
        if (!inc || isNaN(inc) || parseFloat(inc) <= 0) {
            showErr("Please enter a valid monthly income.");
            return;
        }
    }
    hideErr();
    showStep(from + 1);
}

function azBack(from) {
    hideErr();
    showStep(from - 1);
}

function selectLit(val) {
    literacyScore = val;
    document.querySelectorAll(".lit-card").forEach(c => {
        c.classList.toggle("selected", parseInt(c.dataset.val) === val);
    });
}

function showErr(msg) {
    const b = document.getElementById("err-box");
    b.textContent = msg;
    b.style.display = "block";
}
function hideErr() {
    document.getElementById("err-box").style.display = "none";
}

// ── Collect & submit ─────────────────────────────────────

function collectForm() {
    return {
        income:         parseFloat(document.getElementById("income").value),
        city_tier:      document.getElementById("city_tier").value,
        income_type:    document.getElementById("income_type").value,
        dependents:     document.getElementById("dependents").value,
        pf_status:      document.getElementById("pf_status").value,
        emergency_fund: document.getElementById("emergency_fund").value,
        literacy_score: literacyScore,
        bank_distance:  document.getElementById("bank_distance").value,
        first_gen:      document.getElementById("first_gen").value,
        monthly_emi:    parseFloat(document.getElementById("monthly_emi").value) || 0,
        loan_type:      document.getElementById("loan_type").value
    };
}

async function submitForm() {
    hideErr();
    const profile = collectForm();
    window._lastCityTier = profile.city_tier;

    document.getElementById("az-onboarding").style.display = "none";
    document.getElementById("az-loading").style.display    = "block";
    document.getElementById("az-results").style.display    = "none";

    try {
        const res = await fetch(API_URL, {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body:    JSON.stringify(profile)
        });
        if (!res.ok) throw new Error("Server error " + res.status);
        const data = await res.json();
        document.getElementById("az-loading").style.display = "none";
        renderResults(data);
    } catch (err) {
        document.getElementById("az-loading").style.display    = "none";
        document.getElementById("az-onboarding").style.display = "block";
        showErr("Could not connect to backend. Make sure it is running on port 8000.");
    }
}

// ── Reset ────────────────────────────────────────────────

function resetAnalyzer() {
    literacyScore = 1;
    document.getElementById("az-onboarding").style.display = "block";
    document.getElementById("az-loading").style.display    = "none";
    document.getElementById("az-results").style.display    = "none";
    hideErr();
    showStep(1);
    document.querySelectorAll(".lit-card").forEach(c => {
        c.classList.toggle("selected", parseInt(c.dataset.val) === 1);
    });
}

// ── Render results ────────────────────────────────────────

const TYPE_COLORS = {
    emergency_fund:   "#ef5350",
    sip_mutual_fund:  "#609E45",
    index_fund:       "#4ADE80",
    ipo:              "#ffa726",
    short_term:       "#26c6da",
    long_term_equity: "#8b5cf6",
    liquid_fund:      "#78909c",
    debt_payoff:      "#dc2626"
};

function inr(n) {
    return "₹" + Number(n).toLocaleString("en-IN");
}

// ── Stock Recommendations Data ─────────────────────────────

const STOCK_RECOMMENDATIONS = {
    metro: [
        { name: "Parag Parikh Flexi Cap Fund",    type: "Mutual Fund", tag: "flexi",   badge: "Diversified", risk: "Moderate", why: "Pan-India & global diversification. Suits high-income metro investors." },
        { name: "Motilal Oswal Midcap Fund",      type: "Mutual Fund", tag: "midcap",  badge: "Growth",      risk: "Mod-High", why: "Strong mid-cap exposure for wealth compounding over 5+ years." },
        { name: "HDFC Bank",                      type: "Stock",       tag: "bank",    badge: "Blue Chip",   risk: "Low",      why: "India's largest private bank. Anchor holding for stability." },
        { name: "Adani Green Energy",             type: "Stock",       tag: "energy",  badge: "Thematic",    risk: "High",     why: "Leverages India's renewable energy push. High-conviction growth bet." },
        { name: "GoldBees ETF",                   type: "ETF",         tag: "gold",    badge: "Hedge",       risk: "Low",      why: "Gold-backed ETF. Inflation hedge and portfolio stabiliser." },
        { name: "Duroflex IPO",                   type: "IPO",         tag: "ipo",     badge: "Upcoming",    risk: "High",     why: "Consumer lifestyle brand with strong offline-to-online pivot story." },
        { name: "CarDekho IPO",                   type: "IPO",         tag: "ipo",     badge: "Upcoming",    risk: "High",     why: "Auto-tech play riding India's used-car boom. Watch listing premium." },
        { name: "Hindustan Unilever (HINDUNILVR)",type: "Stock",       tag: "fmcg",    badge: "Defensive",   risk: "Low",      why: "FMCG giant. Dividend-paying defensive for volatile periods." },
    ],
    tier1: [
        { name: "NIFTY 50 Dividend Points Index Fund", type: "Index Fund",  tag: "index",   badge: "Passive",    risk: "Low",      why: "Low-cost broad market exposure with dividend compounding." },
        { name: "Motilal Oswal Large & Midcap Fund",   type: "Mutual Fund", tag: "blend",   badge: "Blend",      risk: "Moderate", why: "Best-of-both: large-cap stability + midcap upside." },
        { name: "DSP Natural Resources & New Energy",  type: "Mutual Fund", tag: "thematic",badge: "Thematic",   risk: "Mod-High", why: "Natural resources & clean energy thematic for 7-10 yr horizon." },
        { name: "Kotak Gold & Silver Passive FoF",     type: "ETF",         tag: "gold",    badge: "Hedge",      risk: "Low",      why: "Dual precious-metal hedge. Smart diversifier for Tier-1 savers." },
        { name: "SBI",                                 type: "Stock",       tag: "bank",    badge: "PSU",        risk: "Moderate", why: "India's largest PSU bank. Beneficiary of infra credit growth." },
        { name: "YES Bank",                            type: "Stock",       tag: "bank",    badge: "Turnaround", risk: "High",     why: "Post-restructuring turnaround story. Small allocation only." },
        { name: "SilverBees ETF",                      type: "ETF",         tag: "silver",  badge: "Commodity",  risk: "Moderate", why: "Industrial silver demand surge driven by EV & solar sectors." },
        { name: "ONGC",                                type: "Stock",       tag: "energy",  badge: "Dividend",   risk: "Moderate", why: "High dividend yield PSU. Good for income-seeking investors." },
    ],
    tier2: [
        { name: "Jio BlackRock Low Duration Fund",   type: "Mutual Fund", tag: "debt",    badge: "Low Risk",    risk: "Low",      why: "Capital preservation with better returns than FD. Ideal start." },
        { name: "SBI Automotive Opportunities Fund", type: "Mutual Fund", tag: "thematic",badge: "Thematic",    risk: "Mod-High", why: "Auto sector revival play: EVs, components & OEM growth." },
        { name: "Sovereign Gold Bond (SGB)",         type: "Bond",        tag: "gold",    badge: "Govt. Backed",risk: "Very Low", why: "2.5% annual interest + gold appreciation. Safest gold bet." },
        { name: "NIFTY 50 Dividend Fund",            type: "Index Fund",  tag: "index",   badge: "Passive",     risk: "Low",      why: "Passive index with dividend reinvestment for steady compounding." },
        { name: "HAL (Hindustan Aeronautics)",       type: "Stock",       tag: "defence", badge: "Defence",     risk: "Moderate", why: "Defence manufacturing giant. India's atmanirbhar pivot beneficiary." },
        { name: "Bharti Airtel",                     type: "Stock",       tag: "telecom", badge: "Blue Chip",   risk: "Low",      why: "Telecom leader with ARPU growth and 5G tailwind." },
        { name: "Cochin Shipyard",                   type: "Stock",       tag: "defence", badge: "PSU",         risk: "Moderate", why: "Naval orders + commercial shipbuilding boom. Long runway." },
        { name: "SilverAdd ETF",                     type: "ETF",         tag: "silver",  badge: "Commodity",   risk: "Moderate", why: "Affordable entry into silver with industrial demand tailwinds." },
        { name: "HDFC Bank",                         type: "Stock",       tag: "bank",    badge: "Blue Chip",   risk: "Low",      why: "Evergreen private bank holding for any portfolio tier." },
    ],
    rural: [
        { name: "GoldAdd ETF",              type: "ETF",   tag: "gold",    badge: "Accessible", risk: "Low",      why: "Buy gold digitally via phone. No bank visit needed. Best rural start." },
        { name: "Bharat Forge",             type: "Stock", tag: "mfg",     badge: "Export",     risk: "Moderate", why: "Forging giant serving global auto & defence. Export revenue buffer." },
        { name: "HeroFinCorp IPO",          type: "IPO",   tag: "fintech", badge: "Upcoming",   risk: "Mod-High", why: "NBFC arm of Hero Group catering to semi-urban & rural borrowers." },
        { name: "BEL (Bharat Electronics)", type: "Stock", tag: "defence", badge: "PSU",        risk: "Low",      why: "Defence electronics PSU. Safe, dividend-paying, long order book." },
        { name: "Infosys (INFY)",           type: "Stock", tag: "it",      badge: "Blue Chip",  risk: "Low",      why: "IT giant with global revenue. Stable and highly liquid holding." },
    ]
};

const TAG_COLORS = {
    flexi:    { bg: "#e8f5e9", border: "#4ADE80", text: "#2e7d32" },
    midcap:   { bg: "#fce4ec", border: "#e91e63", text: "#880e4f" },
    bank:     { bg: "#e3f2fd", border: "#2196f3", text: "#0d47a1" },
    energy:   { bg: "#fff3e0", border: "#ff9800", text: "#e65100" },
    gold:     { bg: "#fffde7", border: "#fbc02d", text: "#f57f17" },
    silver:   { bg: "#f5f5f5", border: "#9e9e9e", text: "#424242" },
    ipo:      { bg: "#f3e5f5", border: "#9c27b0", text: "#4a148c" },
    fmcg:     { bg: "#e8f5e9", border: "#66bb6a", text: "#1b5e20" },
    index:    { bg: "#e3f2fd", border: "#42a5f5", text: "#0d47a1" },
    blend:    { bg: "#f1f8e9", border: "#8bc34a", text: "#33691e" },
    thematic: { bg: "#fbe9e7", border: "#ff5722", text: "#bf360c" },
    debt:     { bg: "#e0f7fa", border: "#00bcd4", text: "#006064" },
    bond:     { bg: "#e8eaf6", border: "#5c6bc0", text: "#1a237e" },
    defence:  { bg: "#efebe9", border: "#795548", text: "#3e2723" },
    telecom:  { bg: "#e8eaf6", border: "#3f51b5", text: "#1a237e" },
    mfg:      { bg: "#f9fbe7", border: "#c0ca33", text: "#827717" },
    fintech:  { bg: "#fce4ec", border: "#f06292", text: "#880e4f" },
    it:       { bg: "#e1f5fe", border: "#0288d1", text: "#01579b" },
};

const RISK_COLORS = {
    "Very Low": "#26a69a",
    "Low":      "#43a047",
    "Moderate": "#ffa726",
    "Mod-High": "#ef5350",
    "High":     "#b71c1c",
};

// ── Build recommendations on the MAIN PAGE (outside overlay) ──

function buildPageRecommendations(cityTier) {
    const stocks = STOCK_RECOMMENDATIONS[cityTier] || STOCK_RECOMMENDATIONS["metro"];
    const cityLabels = { metro: "Metro City", tier1: "Tier-1 City", tier2: "Tier-2 City", rural: "Rural / Semi-urban" };

    const sub = document.getElementById("rec-subtitle");
    if (sub) sub.textContent = `Curated picks for ${cityLabels[cityTier] || "your city"} — aligned to your income, literacy level, and financial goals.`;

    const types = ["All", ...new Set(stocks.map(s => s.type))];
    const filterEl = document.getElementById("rec-filters");
    if (filterEl) {
        filterEl.innerHTML = types.map((t, i) =>
            `<button onclick="recFilter(this,'${t}')"
                style="padding:7px 18px;border-radius:50px;
                border:1px solid ${i === 0 ? '#609E45' : '#e0e0e0'};
                background:${i === 0 ? '#609E45' : '#f5f5f5'};
                color:${i === 0 ? '#fff' : '#666'};
                font-size:13px;font-weight:600;cursor:pointer;
                transition:all 0.2s;font-family:inherit;"
                data-type="${t}">${t}</button>`
        ).join('');
    }

    const gridEl = document.getElementById("rec-grid");
    if (gridEl) {
        gridEl.innerHTML = stocks.map((s, idx) => {
            const tc = TAG_COLORS[s.tag] || TAG_COLORS["blend"];
            const rc = RISK_COLORS[s.risk] || "#ffa726";
            return `
            <div class="rec-card" data-type="${s.type}" style="
                background:#f8faf7;border:1px solid rgba(0,0,0,0.06);border-radius:18px;
                padding:22px;position:relative;overflow:hidden;
                transition:transform 0.25s,box-shadow 0.25s,border-color 0.25s;
                animation:recFadeIn 0.4s ease-out ${idx * 0.06}s both;"
                onmouseover="this.style.transform='translateY(-4px)';this.style.boxShadow='0 12px 36px rgba(0,0,0,0.1)';this.style.borderColor='rgba(96,158,69,0.3)'"
                onmouseout="this.style.transform='';this.style.boxShadow='';this.style.borderColor='rgba(0,0,0,0.06)'">
                <div style="position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#609E45,#4ADE80);"></div>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                    <span style="font-size:11px;font-weight:700;padding:3px 10px;border-radius:50px;
                        border:1px solid ${tc.border};background:${tc.bg};color:${tc.text};
                        letter-spacing:0.04em;text-transform:uppercase;">${s.badge}</span>
                    <span style="font-size:11px;font-weight:600;color:${rc};display:flex;align-items:center;gap:4px;">
                        <span style="width:6px;height:6px;border-radius:50%;background:${rc};display:inline-block;"></span>
                        ${s.risk} Risk
                    </span>
                </div>
                <div style="font-size:15px;font-weight:700;color:#1a1a2a;line-height:1.3;margin-bottom:3px;">${s.name}</div>
                <div style="font-size:11px;color:#aaa;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:10px;">${s.type}</div>
                <div style="font-size:13px;color:#666;line-height:1.6;">${s.why}</div>
            </div>`;
        }).join('');
    }

    if (!document.getElementById("rec-anim-style")) {
        const st = document.createElement("style");
        st.id = "rec-anim-style";
        st.textContent = `@keyframes recFadeIn{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}`;
        document.head.appendChild(st);
    }

    const section = document.getElementById("rec-section");
    if (section) {
        section.style.display = "block";
        setTimeout(() => section.scrollIntoView({ behavior: "smooth", block: "start" }), 150);
    }
}

function recFilter(btn, type) {
    document.querySelectorAll("#rec-filters button").forEach(b => {
        b.style.background  = "#f5f5f5";
        b.style.color       = "#666";
        b.style.borderColor = "#e0e0e0";
    });
    btn.style.background  = "#609E45";
    btn.style.color       = "#fff";
    btn.style.borderColor = "#609E45";

    document.querySelectorAll(".rec-card").forEach(card => {
        const show = type === "All" || card.dataset.type === type;
        card.style.display = show ? "" : "none";
        if (show) {
            card.style.opacity   = "0";
            card.style.transform = "translateY(8px)";
            requestAnimationFrame(() => {
                card.style.transition = "opacity 0.3s ease, transform 0.3s ease";
                card.style.opacity    = "1";
                card.style.transform  = "translateY(0)";
            });
        }
    });
}

// ── Render results (inside overlay) ──────────────────────

function renderResults(data) {
    const ps   = data.profile_summary;
    const sb   = data.surplus_breakdown;
    const plan = data.investment_plan;
    const deds = data.equity_deductions;

    document.getElementById("r-headline").textContent = ps.headline;
    document.getElementById("r-submeta").innerHTML =
        `Primary Strategy: <strong>${ps.primary_strategy}</strong>
         &nbsp;·&nbsp; Literacy: <strong>${ps.literacy_level}</strong>`;

    const sEl = document.getElementById("r-strengths");
    sEl.innerHTML = ps.strengths.length
        ? `<div class="slabel g">✅ STRENGTHS</div>` +
          ps.strengths.map(s => `<div class="bitem">· ${s}</div>`).join("") : "";

    const rEl = document.getElementById("r-risks");
    rEl.innerHTML = ps.risks.length
        ? `<div class="slabel a">⚠️ RISK AREAS</div>` +
          ps.risks.map(r => `<div class="bitem">· ${r}</div>`).join("") : "";

    const aEl = document.getElementById("r-actions");
    aEl.innerHTML = ps.actions.length
        ? `<div class="slabel p">🚀 ACTION ITEMS</div>` +
          ps.actions.map(a => `<div class="aitem">${a}</div>`).join("") : "";

    document.getElementById("r-score").textContent = data.equity_score;
    document.getElementById("r-deductions").innerHTML = deds.length
        ? deds.map(d => `<div class="ded-item"><span>${d.points} pts</span> — ${d.reason}</div>`).join("")
        : `<div class="ded-item" style="color:#4ecca3">No penalties — strong financial profile</div>`;

    const wRows = [
        { label: "Raw Monthly Income",           val: sb.raw_income,    cls: "inc" },
        { label: "Cost of Living Adjustment",    val: sb.col_deduction, cls: "ded" },
    ];
    if (sb.emi_deduction > 0)
        wRows.push({ label: "Loan / EMI Payment", val: sb.emi_deduction, cls: "ded" });
    wRows.push(
        { label: "Dependency Load",              val: sb.dep_deduction,       cls: "ded" },
        { label: "Volatility Buffer",            val: sb.vol_deduction,       cls: "ded" },
        { label: "Emergency Fund Gap (monthly)", val: sb.emergency_deduction, cls: "ded" },
    );
    if (sb.debt_acceleration_amount)
        wRows.push({ label: "Debt Acceleration (50%)", val: sb.debt_acceleration_amount, cls: "ded" });
    wRows.push({ label: "True Investable Surplus", val: sb.true_surplus, cls: "sur" });

    document.getElementById("r-waterfall").innerHTML = wRows.map(r => `
        <div class="wrow">
            <span class="wlbl">${r.label}</span>
            <span class="wval ${r.cls}">
                ${r.cls === "inc" ? "+" : r.cls === "ded" ? "−" : ""} ${inr(r.val)}
            </span>
        </div>`).join("");

    document.getElementById("r-allocbar").innerHTML = plan.map(item =>
        `<div style="width:${item.percentage}%;background:${TYPE_COLORS[item.type] || "#7c6fff"}"
              title="${item.label}: ${item.percentage}%"></div>`
    ).join("");

    document.getElementById("r-plan").innerHTML = plan.map(item => `
        <div class="pcard" style="border-left-color:${TYPE_COLORS[item.type] || "#7c6fff"}">
            <div class="ptop">
                <div>
                    <div class="plabel">${item.label}</div>
                    <div class="pmeta">${item.horizon} · ${item.instrument}</div>
                </div>
                <div>
                    <div class="pamount" style="color:${TYPE_COLORS[item.type] || "#7c6fff"}">
                        ${inr(item.monthly_amount)}
                    </div>
                    <div class="ppct">${item.percentage}% of surplus</div>
                </div>
            </div>
            <div class="pwhy">${item.why}</div>
        </div>`).join("");

    document.getElementById("az-results").style.display = "block";

    // Scroll the right panel to top
    const rightPanel = document.querySelector(".az-right");
    if (rightPanel) rightPanel.scrollTop = 0;

    // Inject recommendations inside overlay via #srec-inject
    const cityTier = window._lastCityTier || "metro";
    const injectEl = document.getElementById("srec-inject");
    if (injectEl) {
        injectEl.innerHTML = renderInlineRecommendations(cityTier);
    }

    // Enter results-mode (collapses left panel, expands right)
    if (typeof enterResultsMode === "function") enterResultsMode();
}

// ── Render recommendations INSIDE the overlay ─────────────

function renderInlineRecommendations(cityTier) {
    const stocks = STOCK_RECOMMENDATIONS[cityTier] || STOCK_RECOMMENDATIONS["metro"];
    const cityLabels = { metro: "Metro City", tier1: "Tier-1 City", tier2: "Tier-2 City", rural: "Rural / Semi-urban" };

    // Gather unique types for filter buttons
    const types = ["All", ...new Set(stocks.map(s => s.type))];

    const filterBtns = types.map((t, i) =>
        `<button onclick="srecFilter(this,'${t}')"
            style="padding:5px 14px;border-radius:50px;
            border:1px solid ${i === 0 ? '#609E45' : '#e0e0e0'};
            background:${i === 0 ? '#609E45' : '#f5f5f5'};
            color:${i === 0 ? '#fff' : '#666'};
            font-size:12px;font-weight:600;cursor:pointer;
            transition:all 0.2s;font-family:inherit;margin-bottom:4px;"
            data-type="${t}">${t}</button>`
    ).join('');

    const cards = stocks.map((s, idx) => {
        const tc = TAG_COLORS[s.tag] || TAG_COLORS["blend"];
        const rc = RISK_COLORS[s.risk] || "#ffa726";
        const dashboardUrl = `http://localhost:3000/mutual-funds.html?search=${encodeURIComponent(s.name)}`;
        return `
        <div class="srec-card" data-type="${s.type}" style="
            background:#fff;border:1px solid rgba(0,0,0,0.06);border-radius:14px;
            padding:16px;position:relative;overflow:hidden;cursor:pointer;
            transition:transform 0.2s,box-shadow 0.2s,border-color 0.2s;"
            onclick="window.open('${dashboardUrl}','_blank')"
            onmouseover="this.style.transform='translateY(-3px)';this.style.boxShadow='0 8px 24px rgba(0,0,0,0.08)';this.style.borderColor='rgba(96,158,69,0.3)'"
            onmouseout="this.style.transform='';this.style.boxShadow='';this.style.borderColor='rgba(0,0,0,0.06)'">
            <div style="position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#609E45,#4ADE80);"></div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <span style="font-size:10px;font-weight:700;padding:2px 9px;border-radius:50px;
                    border:1px solid ${tc.border};background:${tc.bg};color:${tc.text};
                    letter-spacing:0.04em;text-transform:uppercase;">${s.badge}</span>
                <span style="font-size:10px;font-weight:600;color:${rc};display:flex;align-items:center;gap:3px;">
                    <span style="width:5px;height:5px;border-radius:50%;background:${rc};display:inline-block;"></span>
                    ${s.risk} Risk
                </span>
            </div>
            <div style="font-size:13.5px;font-weight:700;color:#1a1a2a;line-height:1.3;margin-bottom:2px;">${s.name}</div>
            <div style="font-size:10px;color:#aaa;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;">${s.type}</div>
            <div style="font-size:12px;color:#666;line-height:1.55;margin-bottom:10px;">${s.why}</div>
            <div style="font-size:11px;font-weight:700;color:#609E45;">View in Dashboard →</div>
        </div>`;
    }).join('');

    return `
    <div style="margin-top:4px;margin-bottom:18px;">
        <div style="margin-bottom:10px;">
            <div style="font-size:0.75rem;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#888;margin-bottom:4px;">Suggested Instruments For You</div>
            <div style="font-size:0.78rem;color:#aaa;margin-bottom:12px;">Curated picks for ${cityLabels[cityTier] || "your city"}. Not financial advice — always do your own research.</div>
            <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px;">${filterBtns}</div>
        </div>
        <div id="srec-cards" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            ${cards}
        </div>
    </div>`;
}

function srecFilter(btn, type) {
    // Reset all buttons
    const allBtns = btn.closest('div').querySelectorAll('button');
    allBtns.forEach(b => {
        b.style.background  = "#f5f5f5";
        b.style.color       = "#666";
        b.style.borderColor = "#e0e0e0";
    });
    btn.style.background  = "#609E45";
    btn.style.color       = "#fff";
    btn.style.borderColor = "#609E45";

    document.querySelectorAll(".srec-card").forEach(card => {
        const show = type === "All" || card.dataset.type === type;
        card.style.display = show ? "" : "none";
    });
}