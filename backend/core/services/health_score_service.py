"""
core/services/health_score_service.py
Phase 7 — Financial Health Score

Features:
  - 0-100 score combining:
      1. Savings rate component (up to 40 pts): (income - spend) / income, scaled.
      2. Budget adherence component (up to 30 pts): how well monthly budget limit is respected.
      3. Spending volatility component (up to 30 pts): inverse of the coefficient of variation (CV) of weekly spending.
  - Rule-based financial tips generation keyed to lowest sub-scores.
  - Per-user month-to-date calculation with automatic transaction aggregation.
"""

from __future__ import annotations

import math
import logging
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple

from django.db.models import Sum
from django.contrib.auth.models import User

from ..models import Transaction, UserProfile

logger = logging.getLogger(__name__)


def calculate_financial_health_score(
    income: float,
    spend: float,
    budget_limit: float,
    weekly_spends: List[float],
) -> Dict[str, Any]:
    """
    Pure calculation function for Financial Health Score.
    
    Parameters:
      income: Total monthly income/inflow (₹)
      spend: Total monthly expenditure (₹)
      budget_limit: Monthly budget limit (₹)
      weekly_spends: List of spending amounts across weeks (e.g. 4 weeks)
      
    Returns:
      Dictionary containing total score (0-100), sub-scores, metrics, and actionable tips.
    """
    income = max(0.0, float(income or 0.0))
    spend = max(0.0, float(spend or 0.0))
    budget_limit = max(0.0, float(budget_limit or 0.0))
    weekly_spends = [max(0.0, float(w)) for w in (weekly_spends or [])]

    # ── 1. Savings Rate Component (up to 40 pts) ───────────────────────────
    # Savings rate = (income - spend) / income
    # A 30%+ savings rate achieves the full 40 pts for a student.
    if income > 0.0:
        savings_amount = max(0.0, income - spend) if spend < income else 0.0
        savings_rate = (income - spend) / income
    else:
        savings_amount = 0.0
        savings_rate = 0.0

    if savings_rate <= 0.0:
        savings_score = 0.0
    else:
        # Scale linearly: 30% savings rate (0.30) maps to full 40 pts
        savings_score = round(min(40.0, max(0.0, (savings_rate / 0.30) * 40.0)), 1)

    # ── 2. Budget Adherence Component (up to 30 pts) ───────────────────────
    # Full 30 pts if spend <= budget_limit.
    # Penalized proportionally when spend exceeds budget_limit.
    if budget_limit > 0.0:
        if spend <= budget_limit:
            budget_score = 30.0
            overspend_amount = 0.0
            overspend_ratio = 0.0
        else:
            overspend_amount = spend - budget_limit
            overspend_ratio = overspend_amount / budget_limit
            # Score decays to 0 if overspending by 100%+
            budget_score = round(max(0.0, min(30.0, 30.0 * (1.0 - overspend_ratio))), 1)
    else:
        # If no budget limit defined, fallback to income adherence
        if income > 0.0 and spend <= income:
            budget_score = 30.0
            overspend_amount = 0.0
            overspend_ratio = 0.0
        else:
            budget_score = 15.0
            overspend_amount = max(0.0, spend - income)
            overspend_ratio = (overspend_amount / income) if income > 0 else 0.0

    # ── 3. Spending Volatility Component (up to 30 pts) ────────────────────
    # Inverse of the coefficient of variation (CV = std_dev / mean) of weekly spending.
    # Steadier spending scores higher.
    num_weeks = len(weekly_spends)
    if num_weeks >= 2 and sum(weekly_spends) > 0.0:
        mean_spend = sum(weekly_spends) / num_weeks
        variance = sum((w - mean_spend) ** 2 for w in weekly_spends) / num_weeks
        std_dev = math.sqrt(variance)
        cv = (std_dev / mean_spend) if mean_spend > 0.0 else 0.0
        # Continuous monotonic inverse mapping: 30 / (1 + CV)
        # CV=0 (perfectly steady) -> 30.0 pts
        # CV=0.5 -> 20.0 pts
        # CV=1.0 -> 15.0 pts
        # CV=2.0 -> 10.0 pts
        volatility_score = round(max(0.0, min(30.0, 30.0 / (1.0 + cv))), 1)
    else:
        # If fewer than 2 weeks of data or 0 spend, no erratic volatility observed
        mean_spend = weekly_spends[0] if num_weeks == 1 else 0.0
        std_dev = 0.0
        cv = 0.0
        volatility_score = 30.0

    # ── Total Score & Status Grade ─────────────────────────────────────────
    total_score = round(min(100.0, max(0.0, savings_score + budget_score + volatility_score)), 1)

    if total_score >= 85.0:
        grade = "A+"
        status_label = "Excellent"
        summary_text = "Rock-solid financial discipline! Your spending is steady, within budget, and generating strong savings."
    elif total_score >= 70.0:
        grade = "B"
        status_label = "Good"
        summary_text = "Healthy student financial habits with solid budget control and dependable weekly consistency."
    elif total_score >= 50.0:
        grade = "C"
        status_label = "Fair"
        summary_text = "Moderate financial balance. Minor adjustments to discretionary spending will quickly elevate your score."
    else:
        grade = "D"
        status_label = "Needs Attention"
        summary_text = "Your spending velocity or volatility is putting pressure on your runway. Implement the tips below to regain control."

    # ── Generate Rule-Based Tips (2-3 tips based on lowest sub-scores) ─────
    tips = _generate_health_tips(
        savings_score=savings_score,
        budget_score=budget_score,
        volatility_score=volatility_score,
        savings_rate=savings_rate,
        overspend_ratio=overspend_ratio if budget_limit > 0 else 0.0,
        cv=cv,
        budget_limit=budget_limit,
    )

    return {
        "total_score": total_score,
        "grade": grade,
        "status": status_label,
        "summary": summary_text,
        "components": {
            "savings_rate": {
                "score": savings_score,
                "max_score": 40.0,
                "percentage": round((savings_score / 40.0) * 100.0, 1),
                "actual_rate": round(savings_rate * 100.0, 1),
                "income": round(income, 2),
                "spend": round(spend, 2),
                "saved_amount": round(savings_amount, 2),
            },
            "budget_adherence": {
                "score": budget_score,
                "max_score": 30.0,
                "percentage": round((budget_score / 30.0) * 100.0, 1),
                "budget_limit": round(budget_limit, 2),
                "spend": round(spend, 2),
                "is_within_budget": spend <= budget_limit,
                "overspend_amount": round(overspend_amount, 2),
            },
            "spending_volatility": {
                "score": volatility_score,
                "max_score": 30.0,
                "percentage": round((volatility_score / 30.0) * 100.0, 1),
                "coefficient_of_variation": round(cv, 3),
                "standard_deviation": round(std_dev, 2),
                "mean_weekly_spend": round(mean_spend, 2),
                "weekly_spends": [round(w, 2) for w in weekly_spends],
            },
        },
        "tips": tips,
    }


def _generate_health_tips(
    savings_score: float,
    budget_score: float,
    volatility_score: float,
    savings_rate: float,
    overspend_ratio: float,
    cv: float,
    budget_limit: float,
) -> List[str]:
    """
    Generates 2-3 focused rule-based tips keyed to whichever sub-score is lowest.
    """
    # Normalize sub-scores to [0, 1] ratios
    ratios = [
        ("savings", savings_score / 40.0),
        ("budget", budget_score / 30.0),
        ("volatility", volatility_score / 30.0),
    ]
    # Sort from lowest ratio to highest
    ratios.sort(key=lambda x: x[1])
    lowest_area = ratios[0][0]
    second_lowest_area = ratios[1][0]

    tips: List[str] = []

    # Tips library keyed to areas
    if lowest_area == "savings":
        if savings_rate <= 0.0:
            tips.append("Boost savings: Outflows currently exceed monthly income. Try cutting non-essential deliveries to build a positive cash cushion.")
        else:
            tips.append("Automate your savings: Set a target to transfer ₹500–₹1,000 to your savings goal on the 1st of every month before discretionary spending begins.")
    elif lowest_area == "budget":
        weekly_cap = round(budget_limit / 4.0) if budget_limit > 0 else 2000
        tips.append(f"Cap weekly spending: Break your monthly limit into a strict ₹{weekly_cap:,}/week milestone so you don't exhaust funds mid-month.")
    elif lowest_area == "volatility":
        tips.append("Smooth out weekly spikes: Your spending swings between quiet weekdays and high-spend weekends. Set a dedicated weekend allowance.")

    # Second tip
    if second_lowest_area == "budget" and lowest_area != "budget":
        tips.append("Review big transactions: Use the Review page to spot high-confidence subscriptions or unneeded recurring charges.")
    elif second_lowest_area == "volatility" and lowest_area != "volatility":
        tips.append("Pace larger one-off purchases: Stagger textbooks, clothing, and travel across multiple weeks instead of bunching them together.")
    elif second_lowest_area == "savings" and lowest_area != "savings":
        tips.append("Build a rainy day reserve: Having at least 2 weeks of runway saved protects you from unexpected hostel or academic emergencies.")

    # High performer encouragement
    if len(tips) < 2 or (savings_score >= 35.0 and budget_score >= 26.0 and volatility_score >= 26.0):
        tips.append("Excellent consistency! Consider contributing extra savings towards your active college goals to reach them ahead of schedule.")

    # Return top 2 to 3 unique tips
    unique_tips = []
    for t in tips:
        if t not in unique_tips:
            unique_tips.append(t)
    return unique_tips[:3]


def get_user_financial_health_score(user: User) -> Dict[str, Any]:
    """
    Computes Financial Health Score for a registered User using their current month's
    spending, income, profile budget limit, and 4-week expenditure distribution.
    """
    profile = getattr(user, "profile", None)
    today = date.today()

    # 1. Monthly Income
    # Prefer actual credit transactions over last 30 days, or profile income
    cutoff_30d = today - timedelta(days=30)
    credits_sum = Transaction.objects.filter(
        user=user, is_debit=False, date__gte=cutoff_30d
    ).aggregate(s=Sum("amount"))["s"]
    credits_30d = float(credits_sum or 0.0)

    profile_income = float(profile.monthly_income or 0.0) if profile else 0.0
    profile_budget = float(profile.monthly_budget_limit or 0.0) if profile else 0.0

    if credits_30d > 0.0:
        income = credits_30d
    elif profile_income > 0.0:
        income = profile_income
    elif profile_budget > 0.0:
        income = profile_budget
    else:
        income = 12000.0  # reasonable student baseline

    # 2. Budget Limit
    budget_limit = profile_budget if profile_budget > 0.0 else income

    # 3. Monthly Spend & 4-Week Distribution
    # Query debits over last 28 days to create 4 equal 7-day weekly buckets
    debits_qs = Transaction.objects.filter(
        user=user, is_debit=True, date__gte=cutoff_30d
    )
    total_spend = float(debits_qs.aggregate(s=Sum("amount"))["s"] or 0.0)

    # Split into 4 weekly buckets
    weekly_spends = [0.0, 0.0, 0.0, 0.0]
    for tx in debits_qs:
        if tx.date:
            days_ago = (today - tx.date).days
            week_idx = min(3, max(0, days_ago // 7))
            weekly_spends[3 - week_idx] += float(tx.amount or 0.0)

    # Cold-start fallback if user has no debits yet
    if total_spend == 0.0:
        if profile_budget > 0.0:
            # Baseline estimation
            simulated_spend = profile_budget * 0.75
            weekly_spends = [simulated_spend / 4.0] * 4
            total_spend = simulated_spend
        else:
            weekly_spends = [0.0, 0.0, 0.0, 0.0]

    return calculate_financial_health_score(
        income=income,
        spend=total_spend,
        budget_limit=budget_limit,
        weekly_spends=weekly_spends,
    )
