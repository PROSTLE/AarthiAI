const API_URL = "http://localhost:8000/analyze";

let literacyScore = 1;
let currentStep   = 1;

// ── Open / Close overlay ──────────────────────────────────

function openAnalyzer(e) {
    if (e) e.preventDefault();
    document.getElementById("analyzer-overlay").classList.add("visible");
    document.body.style.overflow = "hidden"; // freeze background scroll
    resetAnalyzer();
}

function closeAnalyzer() {
    document.getElementById("analyzer-overlay").classList.remove("visible");
    document.body.style.overflow = "";
}

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

    // reset literacy cards
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

function renderResults(data) {
    const ps  = data.profile_summary;
    const sb  = data.surplus_breakdown;
    const plan = data.investment_plan;
    const deds = data.equity_deductions;

    // ── Profile headline ──
    document.getElementById("r-headline").textContent = ps.headline;
    document.getElementById("r-submeta").innerHTML =
        `Primary Strategy: <strong>${ps.primary_strategy}</strong>
         &nbsp;·&nbsp; Literacy: <strong>${ps.literacy_level}</strong>`;

    // strengths
    const sEl = document.getElementById("r-strengths");
    sEl.innerHTML = ps.strengths.length
        ? `<div class="slabel g">✅ STRENGTHS</div>` +
          ps.strengths.map(s => `<div class="bitem">· ${s}</div>`).join("")
        : "";

    // risks
    const rEl = document.getElementById("r-risks");
    rEl.innerHTML = ps.risks.length
        ? `<div class="slabel a">⚠️ RISK AREAS</div>` +
          ps.risks.map(r => `<div class="bitem">· ${r}</div>`).join("")
        : "";

    // actions
    const aEl = document.getElementById("r-actions");
    aEl.innerHTML = ps.actions.length
        ? `<div class="slabel p">🚀 ACTION ITEMS</div>` +
          ps.actions.map(a => `<div class="aitem">${a}</div>`).join("")
        : "";

    // equity score
    document.getElementById("r-score").textContent = data.equity_score;
    document.getElementById("r-deductions").innerHTML = deds.length
        ? deds.map(d =>
            `<div class="ded-item"><span>${d.points} pts</span> — ${d.reason}</div>`
          ).join("")
        : `<div class="ded-item" style="color:#4ecca3">No penalties — strong financial profile</div>`;

    // ── Surplus waterfall ──
    const wRows = [
        { label: "Raw Monthly Income",           val: sb.raw_income,          cls: "inc" },
        { label: "Cost of Living Adjustment",    val: sb.col_deduction,       cls: "ded" },
    ];
    if (sb.emi_deduction > 0) {
        wRows.push({ label: "Loan / EMI Payment",  val: sb.emi_deduction,  cls: "ded" });
    }
    wRows.push(
        { label: "Dependency Load",              val: sb.dep_deduction,       cls: "ded" },
        { label: "Volatility Buffer",            val: sb.vol_deduction,       cls: "ded" },
        { label: "Emergency Fund Gap (monthly)", val: sb.emergency_deduction, cls: "ded" },
    );
    if (sb.debt_acceleration_amount) {
        wRows.push({ label: "Debt Acceleration (50%)", val: sb.debt_acceleration_amount, cls: "ded" });
    }
    wRows.push({ label: "True Investable Surplus", val: sb.true_surplus, cls: "sur" });
    document.getElementById("r-waterfall").innerHTML = wRows.map(r => `
        <div class="wrow">
            <span class="wlbl">${r.label}</span>
            <span class="wval ${r.cls}">
                ${r.cls === "inc" ? "+" : r.cls === "ded" ? "−" : ""} ${inr(r.val)}
            </span>
        </div>`).join("");

    // ── Allocation bar ──
    document.getElementById("r-allocbar").innerHTML = plan.map(item =>
        `<div style="width:${item.percentage}%;background:${TYPE_COLORS[item.type]||"#7c6fff"}"
              title="${item.label}: ${item.percentage}%"></div>`
    ).join("");

    // ── Plan cards ──
    document.getElementById("r-plan").innerHTML = plan.map(item => `
        <div class="pcard" style="border-left-color:${TYPE_COLORS[item.type]||"#7c6fff"}">
            <div class="ptop">
                <div>
                    <div class="plabel">${item.label}</div>
                    <div class="pmeta">${item.horizon} · ${item.instrument}</div>
                </div>
                <div>
                    <div class="pamount" style="color:${TYPE_COLORS[item.type]||"#7c6fff"}">
                        ${inr(item.monthly_amount)}
                    </div>
                    <div class="ppct">${item.percentage}% of surplus</div>
                </div>
            </div>
            <div class="pwhy">${item.why}</div>
        </div>`).join("");

    document.getElementById("az-results").style.display = "block";

    // scroll overlay back to top so results are visible from the start
    document.getElementById("analyzer-overlay").scrollTop = 0;
}