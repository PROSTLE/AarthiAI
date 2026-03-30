from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analyzer import (
    compute_surplus,
    generate_allocation,
    generate_investment_plan,
    compute_equity_score,
    build_profile_summary
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class UserProfile(BaseModel):
    income: float
    city_tier: str       # metro | tier1 | tier2 | rural
    income_type: str     # salaried | business | agrarian | seasonal
    dependents: str      # 0 | 1-2 | 3-4 | 5+
    pf_status: str       # epf | ppf | nps | none
    literacy_score: int  # 1 | 2 | 3
    bank_distance: str   # <1km | 1-5km | 5-15km | >15km
    first_gen: str       # first_gen | some_exposure | experienced
    emergency_fund: str  # 0-1 | 2-3 | 4-5 | 6+
    monthly_emi: float = 0.0
    loan_type: str = "none"  # home | education | personal | credit_card | none


@app.post("/analyze")
def analyze(user: UserProfile):
    user_dict = user.dict()

    surplus_breakdown = compute_surplus(user_dict)
    surplus = surplus_breakdown["true_surplus"]

    allocation = generate_allocation(user_dict, surplus)
    investment_plan = generate_investment_plan(user_dict, surplus, allocation, surplus_breakdown)
    equity_score, deductions = compute_equity_score(user_dict, surplus, allocation)
    profile_summary = build_profile_summary(user_dict, surplus, allocation, equity_score)

    return {
        "surplus_breakdown": surplus_breakdown,
        "allocation": allocation,
        "investment_plan": investment_plan,
        "equity_score": equity_score,
        "equity_deductions": deductions,
        "profile_summary": profile_summary
    }