def compute_surplus(user):
    income = user["income"]

    col_rates = {
        "metro": 0.35,
        "tier1": 0.25,
        "tier2": 0.18,
        "rural": 0.10
    }
    col_deduction = income * col_rates.get(user["city_tier"], 0.18)

    # EMI deduction — applied right after COL
    emi_deduction = max(0, float(user.get("monthly_emi", 0)))

    dep_counts = {
        "0": 0, "1-2": 1.5, "3-4": 3.5, "5+": 5
    }
    dep_deduction = dep_counts.get(user["dependents"], 0) * 3000

    vol_rates = {
        "agrarian": 0.20,
        "seasonal": 0.15,
        "business": 0.10,
        "salaried": 0.05
    }
    vol_deduction = income * vol_rates.get(user["income_type"], 0.05)

    months_saved = {
        "0-1": 0.5, "2-3": 2.5, "4-5": 4.5, "6+": 6
    }.get(user["emergency_fund"], 0.5)
    emergency_gap_months = max(0, 6 - months_saved)
    emergency_deduction = (emergency_gap_months * income) / 12

    surplus = income - col_deduction - emi_deduction - dep_deduction - vol_deduction - emergency_deduction
    surplus = max(0, round(surplus))

    # Debt acceleration for high-interest loans
    loan_type = user.get("loan_type", "none")
    debt_acceleration = 0
    if loan_type in ("credit_card", "personal") and surplus > 0:
        debt_acceleration = round(surplus * 0.50)
        surplus = surplus - debt_acceleration

    result = {
        "raw_income": income,
        "col_deduction": round(col_deduction),
        "emi_deduction": round(emi_deduction),
        "dep_deduction": round(dep_deduction),
        "vol_deduction": round(vol_deduction),
        "emergency_deduction": round(emergency_deduction),
        "true_surplus": surplus
    }

    if debt_acceleration > 0:
        result["debt_acceleration_amount"] = debt_acceleration

    return result


def generate_allocation(user, surplus):
    allocation = {
        "emergency_fund": 0,
        "sip_mutual_fund": 0,
        "index_fund": 0,
        "ipo": 0,
        "short_term": 0,
        "long_term_equity": 0,
        "liquid_fund": 0
    }

    literacy    = user["literacy_score"]
    city        = user["city_tier"]
    pf          = user["pf_status"]
    bank_dist   = user["bank_distance"]
    income_type = user["income_type"]
    emergency   = user["emergency_fund"]
    first_gen   = user["first_gen"]

    if emergency in ["0-1", "2-3"]:
        allocation["emergency_fund"] = 30
    elif emergency == "4-5":
        allocation["emergency_fund"] = 15

    remaining = 100 - allocation["emergency_fund"]

    if pf == "none":
        allocation["long_term_equity"] += 20
        remaining -= 20

    if literacy == 1:
        allocation["sip_mutual_fund"] += int(remaining * 0.55)
        allocation["index_fund"]      += int(remaining * 0.35)
        allocation["liquid_fund"]     += int(remaining * 0.10)

    elif literacy == 2:
        allocation["sip_mutual_fund"]  += int(remaining * 0.40)
        allocation["index_fund"]       += int(remaining * 0.25)
        allocation["long_term_equity"] += int(remaining * 0.20)
        allocation["short_term"]       += int(remaining * 0.15)

    else:
        allocation["sip_mutual_fund"]  += int(remaining * 0.25)
        allocation["index_fund"]       += int(remaining * 0.20)
        allocation["long_term_equity"] += int(remaining * 0.25)
        allocation["short_term"]       += int(remaining * 0.20)
        allocation["ipo"]              += int(remaining * 0.10)

    if city == "rural" or bank_dist == ">15km":
        freed = allocation["ipo"]
        allocation["ipo"] = 0
        allocation["sip_mutual_fund"] += freed

    if income_type in ["agrarian", "seasonal"]:
        freed = allocation["short_term"] // 2
        allocation["short_term"] -= freed
        allocation["liquid_fund"] += freed

    total = sum(allocation.values())
    if total != 100 and total > 0:
        allocation["sip_mutual_fund"] += (100 - total)

    return allocation


def generate_investment_plan(user, surplus, allocation, surplus_breakdown=None):
    type_info = {
        "emergency_fund": {
            "label": "Emergency Fund",
            "horizon": "Immediate Priority",
            "instrument": "High-interest savings / Liquid Fund",
            "why": "You don't have enough safety net yet. Build this before anything else."
        },
        "sip_mutual_fund": {
            "label": "SIP — Mutual Fund",
            "horizon": "Long-term (5+ years)",
            "instrument": "ELSS / Large Cap / Flexi Cap",
            "why": "Invest a fixed amount monthly. Builds wealth over time with rupee cost averaging."
        },
        "index_fund": {
            "label": "Index Fund",
            "horizon": "Long-term (7+ years)",
            "instrument": "Nifty 50 / Sensex Index Fund",
            "why": "Lowest cost, no fund manager risk, tracks the market. Best for beginners wanting passive growth."
        },
        "ipo": {
            "label": "IPO Investment",
            "horizon": "Short-term (listing gains) or Long-term",
            "instrument": "Upcoming IPOs via Demat",
            "why": "High potential returns but requires a demat account and tracking IPO calendars."
        },
        "short_term": {
            "label": "Short-Term Fund",
            "horizon": "1–3 years",
            "instrument": "Debt Fund / Short Duration Fund",
            "why": "Better returns than FD for money you'll need within 1–3 years."
        },
        "long_term_equity": {
            "label": "Long-Term Equity",
            "horizon": "10+ years",
            "instrument": "Mid Cap / Small Cap / NPS",
            "why": "Higher risk but significantly higher returns over decade-long horizons. Good retirement substitute if no PF."
        },
        "liquid_fund": {
            "label": "Liquid Fund",
            "horizon": "0–6 months",
            "instrument": "Overnight / Liquid Mutual Fund",
            "why": "Earns better than a savings account. Great for parking money when income is irregular."
        }
    }

    plan = []

    # Insert Debt Payoff card at highest priority if debt acceleration exists
    debt_accel = 0
    if surplus_breakdown:
        debt_accel = surplus_breakdown.get("debt_acceleration_amount", 0)
    if debt_accel > 0:
        loan_type = user.get("loan_type", "unknown")
        loan_label = loan_type.replace("_", " ").title()
        plan.append({
            "type": "debt_payoff",
            "label": f"Debt Payoff — {loan_label}",
            "percentage": 0,  # not part of allocation %
            "monthly_amount": debt_accel,
            "horizon": "Immediate Priority",
            "instrument": f"Accelerated {loan_label} repayment",
            "why": f"You carry high-interest {loan_label.lower()} debt. Paying this off first saves you more than most investments would earn."
        })

    for key, pct in allocation.items():
        if pct > 0:
            amount = round((pct / 100) * surplus)
            if amount > 0:
                info = type_info[key]
                plan.append({
                    "type": key,
                    "label": info["label"],
                    "percentage": pct,
                    "monthly_amount": amount,
                    "horizon": info["horizon"],
                    "instrument": info["instrument"],
                    "why": info["why"]
                })

    # Sort investment items by percentage (debt payoff stays at top with pct=0 trick)
    debt_cards = [p for p in plan if p["type"] == "debt_payoff"]
    invest_cards = [p for p in plan if p["type"] != "debt_payoff"]
    invest_cards.sort(key=lambda x: x["percentage"], reverse=True)
    return debt_cards + invest_cards


def compute_equity_score(user, surplus, allocation):
    score = 100
    deductions = []

    if surplus < 1000:
        score -= 30
        deductions.append({"reason": "True investable surplus is below ₹1,000/month after essential deductions", "points": -30})
    elif surplus < 3000:
        score -= 15
        deductions.append({"reason": "Investable surplus is limited — investment amounts will be small", "points": -15})

    if user["emergency_fund"] == "0-1":
        score -= 20
        deductions.append({"reason": "No emergency fund — financial vulnerability is high", "points": -20})

    if user["pf_status"] == "none":
        score -= 10
        deductions.append({"reason": "No provident fund safety net — retirement gap detected", "points": -10})

    if user["first_gen"] == "first_gen" and allocation.get("ipo", 0) > 0:
        score -= 10
        deductions.append({"reason": "IPO allocation flagged for first-gen investor — consider removing", "points": -10})

    # High Debt-to-Income penalty
    monthly_emi = float(user.get("monthly_emi", 0))
    income = user["income"]
    if income > 0 and monthly_emi > (income * 0.30):
        score -= 20
        deductions.append({"reason": "High Debt-to-Income ratio detected", "points": -20})

    return max(0, score), deductions


def build_profile_summary(user, surplus, allocation, equity_score):
    income = user["income"]
    literacy_labels = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}
    surplus_pct = round((surplus / income) * 100) if income > 0 else 0

    primary = max(allocation, key=allocation.get)
    primary_labels = {
        "sip_mutual_fund":  "SIP-based Mutual Fund investing",
        "index_fund":       "Index Fund investing",
        "long_term_equity": "Long-Term Equity",
        "emergency_fund":   "Building your Emergency Fund",
        "liquid_fund":      "Liquid Fund parking",
        "short_term":       "Short-Term Debt Funds",
        "ipo":              "IPO investments"
    }

    strengths, risks, actions = [], [], []

    if surplus_pct >= 20:
        strengths.append("Strong investable surplus relative to income")
    if user["pf_status"] in ["epf", "ppf", "nps"]:
        strengths.append("Existing retirement safety net through PF coverage")
    if user["emergency_fund"] == "6+":
        strengths.append("Fully funded emergency reserve")
    if user["literacy_score"] == 3:
        strengths.append("Advanced financial literacy enables broader investment options")

    if user["emergency_fund"] in ["0-1", "2-3"]:
        risks.append("Emergency fund below 6-month target — vulnerable to income shocks")
    if user["income_type"] in ["agrarian", "seasonal"]:
        risks.append("Irregular income requires a higher liquidity buffer")
    if user["city_tier"] == "rural" and user["bank_distance"] == ">15km":
        risks.append("Physical banking access constraints may limit investment options")
    if user["first_gen"] == "first_gen":
        risks.append("First-generation investor — extra care needed with complex products")
    monthly_emi = float(user.get("monthly_emi", 0))
    if monthly_emi > 0 and income > 0 and monthly_emi > (income * 0.30):
        risks.append("High Debt-to-Income ratio — EMI exceeds 30% of gross income")

    loan_type = user.get("loan_type", "none")
    if loan_type in ("credit_card", "personal"):
        loan_label = loan_type.replace("_", " ").title()
        actions.append(f"Priority 0: Aggressively pay off {loan_label.lower()} debt before investing")
    if user["emergency_fund"] in ["0-1", "2-3"]:
        actions.append("Priority 1: Build emergency fund to 6 months before aggressive investing")
    if user["pf_status"] == "none":
        actions.append("Open a PPF or NPS account for long-term retirement security")
    if user["literacy_score"] == 1:
        actions.append("Start with index funds — lowest cost and simplest to understand")
    if user["city_tier"] == "rural":
        actions.append("Use PhonePe / Paytm Money / Groww for demat-free SIP investing")

    return {
        "headline": f"Your true investable surplus is ₹{surplus:,}/month ({surplus_pct}% of income)",
        "primary_strategy": primary_labels.get(primary, "SIP investing"),
        "literacy_level": literacy_labels.get(user["literacy_score"], "Beginner"),
        "strengths": strengths,
        "risks": risks,
        "actions": actions,
        "equity_score": equity_score
    }