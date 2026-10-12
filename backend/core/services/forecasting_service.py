"""
core/services/forecasting_service.py
Phase 5 — Spending Forecasting & Cash-Flow Runway Simulator

Features:
  - Per-user 30-day daily spend forecasting using Prophet (or ARIMA fallback).
  - Cold-start handling (<14 days of data) via baseline daily average.
  - Cash-flow runway calculation (projected date funds run out based on current balance).
  - What-If simulator adjusting category spending (e.g. reduce Food by 30%) and
    recomputing runway date and money saved live.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd
from django.db.models import Sum
from django.contrib.auth.models import User

from ..models import Transaction, UserProfile, ExpenseCategory

logger = logging.getLogger(__name__)

# Check if Prophet is installed
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False

try:
    from statsmodels.tsa.arima.model import ARIMA
    ARIMA_AVAILABLE = True
except ImportError:
    ARIMA_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data Extraction & History Helpers
# ---------------------------------------------------------------------------

def get_user_spending_data(
    user: User,
    lookback_days: int = 90,
) -> Tuple[pd.DataFrame, Dict[str, float], float]:
    """
    Retrieves user's historical daily debit spending and category distribution.
    Returns:
      (daily_df, category_shares_dict, overall_daily_avg)
    """
    cutoff = date.today() - timedelta(days=lookback_days)
    txns = Transaction.objects.filter(
        user=user,
        is_debit=True,
        is_deleted=False,
        is_duplicate=False,
        date__isnull=False,
    ).order_by("date")

    if not txns.exists():
        return pd.DataFrame(columns=["date", "amount"]), {}, 0.0

    # Group by date
    daily_records = []
    category_totals = {}
    total_spend = 0.0

    for tx in txns:
        amt = float(tx.amount or 0.0)
        total_spend += amt
        cat = tx.category or ExpenseCategory.OTHER
        category_totals[cat] = category_totals.get(cat, 0.0) + amt

    # Category shares (fraction of total spending)
    category_shares = {}
    if total_spend > 0:
        for cat, c_amt in category_totals.items():
            category_shares[cat] = round(c_amt / total_spend, 4)
    else:
        # Default even shares
        for cat in ExpenseCategory.values:
            category_shares[cat] = round(1.0 / len(ExpenseCategory.values), 4)

    # Aggregate daily amounts
    daily_qs = (
        txns.values("date")
        .annotate(total=Sum("amount"))
        .order_by("date")
    )
    for r in daily_qs:
        daily_records.append({
            "date": r["date"],
            "amount": float(r["total"] or 0.0),
        })

    daily_df = pd.DataFrame(daily_records)
    if not daily_df.empty:
        daily_df["date"] = pd.to_datetime(daily_df["date"])
        daily_avg = float(daily_df["amount"].mean())
    else:
        daily_avg = 0.0

    return daily_df, category_shares, daily_avg


# ---------------------------------------------------------------------------
# Forecasting Engine (Prophet -> ARIMA -> Cold-Start Average)
# ---------------------------------------------------------------------------

def forecast_daily_spending(
    user: User,
    steps: int = 30,
) -> Dict[str, Any]:
    """
    Forecasts daily spend for the next `steps` days.
    Selects method based on data availability:
      - If < 14 distinct dates: 'baseline_average' (cold start fallback)
      - If Prophet available: 'prophet'
      - Otherwise: 'arima'
    """
    daily_df, category_shares, daily_avg = get_user_spending_data(user)
    distinct_days = len(daily_df)

    start_date = date.today() + timedelta(days=1)
    future_dates = [start_date + timedelta(days=i) for i in range(steps)]
    forecast_values = []
    method_used = "baseline_average"

    # Fallback default spend if no history at all
    if daily_avg <= 0:
        profile = getattr(user, "profile", None)
        budget = float(profile.monthly_budget_limit or 0.0) if profile else 0.0
        income = float(profile.monthly_income or 0.0) if profile else 0.0
        base_monthly = budget if budget > 0 else (income if income > 0 else 6000.0)
        daily_avg = round(base_monthly / 30.0, 2)

    # 1. Cold-start case (< 14 distinct days)
    if distinct_days < 14:
        method_used = "baseline_average"
        # Add realistic day-of-week variation (weekends slightly higher)
        for d in future_dates:
            dow = d.weekday()
            multiplier = 1.15 if dow in (4, 5, 6) else 0.90
            forecast_values.append(round(daily_avg * multiplier, 2))

    # 2. Prophet model (if installed and >= 14 days)
    elif PROPHET_AVAILABLE:
        try:
            m = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=False,
            )
            df_p = daily_df.rename(columns={"date": "ds", "amount": "y"})
            m.fit(df_p)
            future = m.make_future_dataframe(periods=steps, include_history=False)
            pred = m.predict(future)
            raw_vals = pred["yhat"].values
            forecast_values = [max(10.0, round(float(v), 2)) for v in raw_vals]
            method_used = "prophet"
        except Exception as e:
            logger.warning("Prophet fit failed: %s, falling back to ARIMA", e)
            method_used = None

    # 3. ARIMA model (fallback or primary if Prophet not present)
    if not forecast_values and ARIMA_AVAILABLE and distinct_days >= 14:
        try:
            series = daily_df["amount"].values
            order = (1, 0, 1) if distinct_days >= 20 else (1, 0, 0)
            arima_model = ARIMA(series, order=order)
            fit_res = arima_model.fit()
            raw_preds = fit_res.forecast(steps=steps)
            forecast_values = [max(10.0, round(float(v), 2)) for v in raw_preds]
            method_used = "arima"
        except Exception as e:
            logger.warning("ARIMA fit failed: %s, falling back to baseline average", e)
            method_used = "baseline_average"

    # Final fallback if both Prophet and ARIMA failed
    if not forecast_values:
        method_used = "baseline_average"
        for d in future_dates:
            dow = d.weekday()
            multiplier = 1.15 if dow in (4, 5, 6) else 0.90
            forecast_values.append(round(daily_avg * multiplier, 2))

    # Historical series for charting (last 14 days of actual data)
    historical_points = []
    if not daily_df.empty:
        recent_df = daily_df.tail(14)
        for _, row in recent_df.iterrows():
            historical_points.append({
                "date": row["date"].strftime("%Y-%m-%d"),
                "actual": round(float(row["amount"]), 2),
                "forecast": None,
            })

    return {
        "future_dates": [d.strftime("%Y-%m-%d") for d in future_dates],
        "forecast_values": forecast_values,
        "daily_avg": round(float(np.mean(forecast_values)), 2),
        "category_shares": category_shares,
        "historical_points": historical_points,
        "method": method_used,
        "distinct_days_history": distinct_days,
    }


# ---------------------------------------------------------------------------
# Runway Calculation Engine
# ---------------------------------------------------------------------------

def calculate_cash_flow_runway(
    user: User,
    current_balance: Optional[float] = None,
    forecast_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Simulates cumulative spending against balance to calculate the runway date.
    Returns:
      - current_balance: float
      - runway_days: int
      - runway_date: 'YYYY-MM-DD'
      - is_exhausted: bool
      - forecast_series: list of chart points with balance trajectory
    """
    if forecast_data is None:
        forecast_data = forecast_daily_spending(user)

    # Determine starting balance
    if current_balance is not None:
        balance = float(current_balance)
    else:
        # Infer balance: monthly income (or budget) - spend so far this month
        profile = getattr(user, "profile", None)
        income = float(profile.monthly_income or 0.0) if profile else 0.0
        budget = float(profile.monthly_budget_limit or 0.0) if profile else 0.0
        base_fund = income if income > 0 else (budget if budget > 0 else 10000.0)

        # Spending so far this month
        today = date.today()
        month_debits = (
            Transaction.objects.filter(
                user=user,
                is_debit=True,
                is_deleted=False,
                is_duplicate=False,
                date__year=today.year,
                date__month=today.month,
            ).aggregate(total=Sum("amount"))["total"]
            or 0.0
        )
        balance = max(0.0, base_fund - float(month_debits))

    balance = round(balance, 2)
    starting_balance = balance

    dates = forecast_data["future_dates"]
    spends = forecast_data["forecast_values"]
    daily_avg = forecast_data["daily_avg"]

    runway_days = None
    runway_date = None
    is_exhausted = False

    series = []
    # Add today's starting point
    series.append({
        "date": date.today().strftime("%Y-%m-%d"),
        "actual": None,
        "forecast": 0.0,
        "balance_remaining": starting_balance,
        "daily_spend": 0.0,
    })

    remaining_bal = starting_balance

    for i, (d_str, day_spend) in enumerate(zip(dates, spends), start=1):
        remaining_bal = max(0.0, remaining_bal - day_spend)
        series.append({
            "date": d_str,
            "actual": None,
            "forecast": day_spend,
            "balance_remaining": round(remaining_bal, 2),
            "daily_spend": day_spend,
        })

        if remaining_bal <= 0 and runway_days is None:
            runway_days = i
            runway_date = d_str
            is_exhausted = True

    # If funds last beyond the 30-day window
    if runway_days is None:
        is_exhausted = False
        if daily_avg > 0 and remaining_bal > 0:
            extra_days = int(remaining_bal / daily_avg)
            runway_days = len(dates) + extra_days
            projected_d = date.today() + timedelta(days=runway_days)
            runway_date = projected_d.strftime("%Y-%m-%d")
        else:
            runway_days = len(dates)
            runway_date = dates[-1]

    # Prepend historical actuals to the chart series
    full_chart_series = []
    for h in forecast_data.get("historical_points", []):
        full_chart_series.append({
            "date": h["date"],
            "actual": h["actual"],
            "forecast": None,
            "balance_remaining": None,
        })
    full_chart_series.extend(series)

    return {
        "current_balance": starting_balance,
        "runway_days": runway_days,
        "runway_date": runway_date,
        "is_exhausted": is_exhausted,
        "daily_burn_rate": daily_avg,
        "forecast_series": full_chart_series,
        "category_shares": forecast_data["category_shares"],
        "method": forecast_data["method"],
        "distinct_days_history": forecast_data["distinct_days_history"],
    }


# ---------------------------------------------------------------------------
# What-If Simulator Engine
# ---------------------------------------------------------------------------

def simulate_whatif_adjustments(
    user: User,
    adjustments: Any,
    current_balance: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Accepts category spending adjustments:
      e.g. {"category": "Food", "reduce_percent": 30}
      or {"adjustments": [{"category": "Food", "reduce_percent": 30}, ...]}
      or {"adjustments": {"Food": 30, "Entertainment": 50}}

    Recomputes daily spend series, adjusted runway date, days saved, and money saved.
    """
    # 1. Base forecast and baseline runway
    forecast_data = forecast_daily_spending(user)
    base_runway = calculate_cash_flow_runway(
        user=user,
        current_balance=current_balance,
        forecast_data=forecast_data,
    )

    # 2. Parse adjustments into a dict: { category: reduce_percent }
    adj_map: Dict[str, float] = {}

    if isinstance(adjustments, dict):
        if "category" in adjustments and "reduce_percent" in adjustments:
            adj_map[str(adjustments["category"])] = float(adjustments["reduce_percent"])
        elif "adjustments" in adjustments:
            inner = adjustments["adjustments"]
            if isinstance(inner, dict):
                for k, v in inner.items():
                    adj_map[str(k)] = float(v)
            elif isinstance(inner, list):
                for item in inner:
                    if isinstance(item, dict) and "category" in item:
                        adj_map[str(item["category"])] = float(item.get("reduce_percent", 0.0))
        else:
            for k, v in adjustments.items():
                if k in ExpenseCategory.values:
                    adj_map[k] = float(v)
    elif isinstance(adjustments, list):
        for item in adjustments:
            if isinstance(item, dict) and "category" in item:
                adj_map[str(item["category"])] = float(item.get("reduce_percent", 0.0))

    # 3. Compute overall percentage reduction on daily spending
    category_shares = forecast_data["category_shares"]
    total_reduction_factor = 0.0

    for cat_name, red_pct in adj_map.items():
        # Match case-insensitively with category shares
        share = 0.0
        for known_cat, sh in category_shares.items():
            if known_cat.lower() == cat_name.lower():
                share = sh
                break
        if share == 0.0:
            share = 0.15  # Reasonable default share if category has no history yet

        clamped_red = max(0.0, min(100.0, float(red_pct))) / 100.0
        total_reduction_factor += share * clamped_red

    # Clamp reduction factor between 0.0 and 0.90 (cannot reduce to 0 or negative)
    total_reduction_factor = min(0.90, max(0.0, total_reduction_factor))

    # 4. Compute adjusted daily spending
    base_spends = forecast_data["forecast_values"]
    adjusted_spends = [
        round(max(5.0, val * (1.0 - total_reduction_factor)), 2)
        for val in base_spends
    ]

    adj_forecast_data = dict(forecast_data)
    adj_forecast_data["forecast_values"] = adjusted_spends
    adj_forecast_data["daily_avg"] = round(float(np.mean(adjusted_spends)), 2)

    # 5. Recompute runway with adjusted spends
    adj_runway = calculate_cash_flow_runway(
        user=user,
        current_balance=base_runway["current_balance"],
        forecast_data=adj_forecast_data,
    )

    # 6. Calculate savings
    money_saved_30d = round(sum(base_spends) - sum(adjusted_spends), 2)
    days_saved = max(0, (adj_runway["runway_days"] or 0) - (base_runway["runway_days"] or 0))

    return {
        "original_runway_date": base_runway["runway_date"],
        "original_runway_days": base_runway["runway_days"],
        "adjusted_runway_date": adj_runway["runway_date"],
        "adjusted_runway_days": adj_runway["runway_days"],
        "days_saved": days_saved,
        "money_saved_30d": money_saved_30d,
        "total_reduction_percent": round(total_reduction_factor * 100, 1),
        "applied_adjustments": adj_map,
        "current_balance": base_runway["current_balance"],
        "adjusted_daily_burn": adj_runway["daily_burn_rate"],
        "adjusted_forecast_series": adj_runway["forecast_series"],
    }
