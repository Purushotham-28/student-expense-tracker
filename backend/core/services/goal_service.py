"""
core/services/goal_service.py
Phase 6 — Goal Planner & Adaptive Savings Service

Features:
  - Goal progress tracking and adaptive weekly savings target recalculation.
  - Background-style health check comparing actual recent savings rate to needed rate.
  - Intelligent discretionary category trim suggestions using Phase 5 forecasting.
  - Contribution logging and automatic completion status transition.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

from django.db.models import Sum
from django.contrib.auth.models import User

from ..models import Goal, Transaction, UserProfile, ExpenseCategory
from .forecasting_service import (
    get_user_spending_data,
    forecast_daily_spending,
    simulate_whatif_adjustments,
)

logger = logging.getLogger(__name__)

# Categories prioritized for budget trimming (discretionary spending)
TRIMMABLE_CATEGORIES = [
    ExpenseCategory.FOOD,
    ExpenseCategory.ENTERTAINMENT,
    ExpenseCategory.GROCERIES_SHOPPING,
    ExpenseCategory.SUBSCRIPTIONS,
    ExpenseCategory.OTHER,
    ExpenseCategory.TRAVEL,
]

# Non-discretionary categories that should be spared from cuts if possible
PROTECTED_CATEGORIES = [
    ExpenseCategory.RENT_HOSTEL,
    ExpenseCategory.ACADEMICS,
]


def calculate_goal_metrics(goal: Goal) -> Dict[str, Any]:
    """
    Computes real-time progress metrics and adaptive weekly targets for a Goal.
    """
    target = float(goal.target_amount or 0.0)
    saved = float(goal.saved_so_far or 0.0)
    remaining = max(0.0, target - saved)
    weeks = goal.weeks_remaining
    weekly_target = goal.weekly_target
    progress_pct = goal.progress_percentage
    is_completed = goal.status == Goal.Status.DONE or saved >= target

    today = date.today()
    days_remaining = (goal.deadline - today).days

    return {
        "id": goal.id,
        "name": goal.name,
        "target_amount": target,
        "saved_so_far": saved,
        "remaining_amount": round(remaining, 2),
        "deadline": goal.deadline.isoformat(),
        "days_remaining": days_remaining,
        "weeks_remaining": weeks,
        "weekly_target": weekly_target,
        "progress_percentage": progress_pct,
        "status": goal.status,
        "is_completed": is_completed,
    }


def contribute_to_goal(
    goal: Goal,
    amount: float | Decimal,
) -> Tuple[Goal, bool]:
    """
    Adds funds to goal.saved_so_far. If target reached, automatically marks status as done.
    Returns (updated_goal, just_completed).
    """
    was_done = goal.status == Goal.Status.DONE
    target = float(goal.target_amount or 0.0)

    amount_dec = Decimal(str(amount))
    goal.saved_so_far = Decimal(str(float(goal.saved_so_far) + float(amount_dec)))

    just_completed = False
    if float(goal.saved_so_far) >= target:
        goal.status = Goal.Status.DONE
        if not was_done:
            just_completed = True

    goal.save(update_fields=["saved_so_far", "status", "updated_at"])
    return goal, just_completed


def check_goal_progress_and_suggest_cut(
    user: User,
    goal_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Background-style check (called on dashboard load or on-demand):
    1. Evaluates user's active savings goals and calculates needed weekly savings rate.
    2. Measures actual recent weekly savings rate (inflow - outflow over last 30 days).
    3. Flags if the student is falling behind.
    4. If behind, leverages the Phase 5 forecasting engine to identify the best
       discretionary category to trim and computes recommended reduction percentage,
       estimated weekly savings, and what-if simulation impact.
    """
    active_goals_qs = Goal.objects.filter(user=user, status=Goal.Status.ACTIVE)
    if goal_id:
        active_goals_qs = active_goals_qs.filter(id=goal_id)

    active_goals = list(active_goals_qs)
    total_active_goals = len(active_goals)

    if total_active_goals == 0:
        return {
            "has_active_goals": False,
            "is_behind": False,
            "needed_weekly_rate": 0.0,
            "actual_weekly_savings_rate": 0.0,
            "weekly_deficit": 0.0,
            "suggested_category": None,
            "recommended_reduction_percent": 0,
            "projected_weekly_savings": 0.0,
            "message": "You currently have no active savings goals. Create one to start tracking!",
            "goals_summary": [],
        }

    # Sum of needed weekly targets across active goals
    needed_weekly_rate = round(sum(g.weekly_target for g in active_goals), 2)

    # 1. Measure recent cash flow over past 30 days
    today = date.today()
    cutoff_30d = today - timedelta(days=30)

    debit_txns = Transaction.objects.filter(
        user=user,
        is_debit=True,
        is_deleted=False,
        is_duplicate=False,
        date__gte=cutoff_30d,
    )
    total_debit_30d = float(debit_txns.aggregate(s=Sum("amount"))["s"] or 0.0)

    credit_txns = Transaction.objects.filter(
        user=user,
        is_debit=False,
        is_deleted=False,
        is_duplicate=False,
        date__gte=cutoff_30d,
    )
    total_credit_30d = float(credit_txns.aggregate(s=Sum("amount"))["s"] or 0.0)

    # Check user profile for monthly allowance / income
    profile = getattr(user, "profile", None)
    profile_income = float(profile.monthly_income or 0.0) if profile else 0.0
    profile_budget = float(profile.monthly_budget_limit or 0.0) if profile else 0.0

    # Inflow estimate: prefer actual credits if available, then profile income, then budget fallback
    if total_credit_30d > 0:
        monthly_inflow = total_credit_30d
    elif profile_income > 0:
        monthly_inflow = profile_income
    elif profile_budget > 0:
        monthly_inflow = profile_budget
    else:
        monthly_inflow = 12000.0  # standard baseline for student

    weekly_inflow = round(monthly_inflow / 4.2857, 2)  # ~30/7 weeks
    weekly_spend = round(total_debit_30d / 4.2857, 2) if total_debit_30d > 0 else 0.0

    # If user has no debit transactions yet, estimate from profile budget
    if weekly_spend == 0.0 and profile_budget > 0:
        weekly_spend = round(profile_budget / 4.2857, 2)

    actual_weekly_savings = round(weekly_inflow - weekly_spend, 2)
    # Falling behind condition
    is_behind = (actual_weekly_savings < needed_weekly_rate) or (needed_weekly_rate > 0 and actual_weekly_savings <= 0)
    weekly_deficit = max(0.0, round(needed_weekly_rate - actual_weekly_savings, 2))

    # 2. Category trim suggestion using Phase 5 Forecasting Engine
    suggested_category = "Food"
    recommended_reduction_percent = 20
    projected_weekly_savings = 0.0
    whatif_impact = {}

    # Extract historical spending distribution & 30-day forecast
    daily_df, category_shares, overall_avg = get_user_spending_data(user, lookback_days=90)
    forecast_result = forecast_daily_spending(user, steps=30)
    forecast_30d_total = forecast_result.get("total_projected_spend", 0.0)

    # Find highest discretionary spend category
    category_weekly_estimates: Dict[str, float] = {}
    for cat in TRIMMABLE_CATEGORIES:
        share = category_shares.get(cat, 0.0)
        # Normalize fraction vs percentage
        frac = share if share <= 1.0 else (share / 100.0)
        cat_30d = forecast_30d_total * frac if frac > 0 else 0.0
        cat_weekly = cat_30d / 4.2857
        if cat_weekly > 0:
            category_weekly_estimates[cat] = cat_weekly

    # If user has recorded transactions in trimmable categories, pick top
    if category_weekly_estimates:
        sorted_cats = sorted(category_weekly_estimates.items(), key=lambda x: x[1], reverse=True)
        suggested_category, top_weekly_spend = sorted_cats[0]
    else:
        # Default cold-start fallback
        suggested_category = ExpenseCategory.FOOD
        top_weekly_spend = round((weekly_spend or (weekly_inflow * 0.4)) * 0.5, 2)

    if is_behind and top_weekly_spend > 0:
        # Calculate reduction % needed to cover deficit
        needed_pct = (weekly_deficit / top_weekly_spend) * 100.0
        # Clamp to realistic student range (10% to 45%) rounded to nearest 5%
        clamped_pct = min(45, max(10, int(round(needed_pct / 5.0) * 5)))
        recommended_reduction_percent = clamped_pct
        projected_weekly_savings = round(top_weekly_spend * (recommended_reduction_percent / 100.0), 2)
    elif not is_behind:
        recommended_reduction_percent = 0
        projected_weekly_savings = 0.0
    else:
        recommended_reduction_percent = 25
        projected_weekly_savings = round(top_weekly_spend * 0.25, 2)

    # Run what-if adjustment simulator for context
    try:
        whatif_impact = simulate_whatif_adjustments(
            user=user,
            adjustments={suggested_category: recommended_reduction_percent},
        )
    except Exception as e:
        logger.warning(f"Could not compute what-if impact for suggestion: {e}")
        whatif_impact = {
            "runway_days_gained": 7,
            "thirty_day_savings": round(projected_weekly_savings * 4.2857, 2),
        }

    # Generate message
    if is_behind:
        message = (
            f"You need ₹{needed_weekly_rate:,.0f}/week to stay on schedule, but your current savings rate "
            f"is ₹{max(0.0, actual_weekly_savings):,.0f}/week (gap of ₹{weekly_deficit:,.0f}/week). "
            f"Trimming your {suggested_category} expenses by {recommended_reduction_percent}% "
            f"can free up ~₹{projected_weekly_savings:,.0f}/week and get you back on track!"
        )
    else:
        message = (
            f"Great momentum! Your current weekly savings rate of ₹{actual_weekly_savings:,.0f}/week "
            f"covers your required weekly target of ₹{needed_weekly_rate:,.0f}/week."
        )

    return {
        "has_active_goals": True,
        "is_behind": is_behind,
        "needed_weekly_rate": needed_weekly_rate,
        "actual_weekly_savings_rate": actual_weekly_savings,
        "weekly_deficit": weekly_deficit,
        "suggested_category": suggested_category,
        "recommended_reduction_percent": recommended_reduction_percent,
        "projected_weekly_savings": projected_weekly_savings,
        "projected_monthly_savings": round(projected_weekly_savings * 4.2857, 2),
        "runway_days_gained": whatif_impact.get("runway_days_gained", 0),
        "message": message,
        "goals_count": total_active_goals,
        "goals_summary": [calculate_goal_metrics(g) for g in active_goals],
    }
