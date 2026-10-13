"""
dashboard_service.py — Aggregates all Phase 1-8 domain services into a unified,
demo-ready dashboard summary for the student.

Computes:
1. Budget vs Actual this month (allowance, spent, remaining, % consumed, burn rate)
2. Category Breakdown with budget shares, percentages, and icons
3. Budget Alerts: triggered when any category crosses 80% or 100% of its budget share
4. Cash-Flow Runway summary (runway date, days, burn rate, forecast series)
5. Goals Progress & adaptive weekly savings velocity
6. Financial Health Score (0-100 gauge with sub-scores & tips)
7. Recent transactions & verification pipeline status counts
"""

from datetime import date, datetime
import calendar
from decimal import Decimal
from typing import Dict, Any, List

from django.contrib.auth.models import User
from django.db.models import Sum

from ..models import Transaction, Goal, UserProfile
from .forecasting_service import calculate_cash_flow_runway
from .goal_service import check_goal_progress_and_suggest_cut
from .health_score_service import get_user_financial_health_score
from .categorization_service import CATEGORIES

# Default campus budget share distribution per category
CATEGORY_BENCHMARK_SHARES = {
    'Food': 0.28,               # 28% of monthly budget
    'Rent/Hostel': 0.22,        # 22%
    'Groceries/Shopping': 0.12, # 12%
    'Utilities': 0.08,          # 8%
    'Travel': 0.08,             # 8%
    'Entertainment': 0.06,      # 6%
    'Academics': 0.06,          # 6%
    'Stationery': 0.04,         # 4%
    'Subscriptions': 0.03,      # 3%
    'Friend/Split': 0.04,       # 4%
    'Other': 0.04,              # 4%
}

CATEGORY_METADATA = {
    'Food': {'icon': '🍔', 'color': '#f59e0b'},
    'Travel': {'icon': '🚗', 'color': '#3b82f6'},
    'Groceries/Shopping': {'icon': '🛒', 'color': '#10b981'},
    'Subscriptions': {'icon': '📺', 'color': '#8b5cf6'},
    'Rent/Hostel': {'icon': '🏠', 'color': '#ef4444'},
    'Academics': {'icon': '📚', 'color': '#06b6d4'},
    'Stationery': {'icon': '✏️', 'color': '#14b8a6'},
    'Utilities': {'icon': '💡', 'color': '#eab308'},
    'Friend/Split': {'icon': '👥', 'color': '#ec4899'},
    'Entertainment': {'icon': '🎬', 'color': '#f97316'},
    'Other': {'icon': '🏷️', 'color': '#64748b'},
}


def get_available_months_for_user(user: User) -> List[str]:
    """
    Returns a sorted list of unique months ('YYYY-MM') for the user to check in spending breakdown.
    Includes all 12 calendar months for the current year (January through December),
    plus all 12 calendar months for any other year where the user has recorded transactions.
    """
    today = date.today()
    month_keys = set()

    # All 12 calendar months of current year
    for m in range(1, 13):
        month_keys.add(f"{today.year:04d}-{m:02d}")

    # Discover all years where transactions exist for this user
    tx_dates = Transaction.objects.filter(
        user=user,
        is_deleted=False,
        date__isnull=False,
    ).values_list("date", flat=True)

    for d in tx_dates:
        if d:
            for m in range(1, 13):
                month_keys.add(f"{d.year:04d}-{m:02d}")

    return sorted(list(month_keys))


def get_category_breakdown_for_month(
    user: User,
    year: Any = None,
    month: Any = None,
) -> Dict[str, Any]:
    """
    Computes category breakdown, budget adherence, and alerts for a given month and year.
    Defaults to the current month/year if not provided.
    Supports month='all' to aggregate category breakdown across all months of a year (or all time).
    Filters out soft-deleted and duplicate transactions.
    """
    today = date.today()

    is_all_months = False
    if month is not None and str(month).lower() in ('all', 'all-months', 'total'):
        is_all_months = True

    target_year = today.year
    target_month = today.month

    if year is not None and str(year).lower() != 'all':
        try:
            y = int(year)
            if 2000 <= y <= 2100:
                target_year = y
        except (ValueError, TypeError):
            pass

    if not is_all_months and month is not None:
        try:
            m = int(month)
            if 1 <= m <= 12:
                target_month = m
        except (ValueError, TypeError):
            pass

    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={'college_roll_number': f'ROLL-{user.id}', 'monthly_budget_limit': 15000.0},
    )
    monthly_budget_limit = float(profile.monthly_budget_limit or 15000.0)
    monthly_income = float(profile.monthly_income or 0.0)
    all_user_txs = Transaction.objects.filter(user=user, is_deleted=False, is_duplicate=False)

    if is_all_months:
        is_current_month = False
        start_of_month = date(target_year, 1, 1)
        end_of_month = date(target_year, 12, 31)
        days_in_month = 365
        days_passed = days_in_month if target_year < today.year else today.timetuple().tm_yday
        days_remaining = max(0, days_in_month - days_passed)
        effective_budget_limit = monthly_budget_limit * 12.0

        month_txs = all_user_txs.filter(
            is_debit=True,
            date__gte=start_of_month,
            date__lte=end_of_month,
        )
        month_label = f"All Months ({target_year})"
        month_key = f"{target_year}-all"
    else:
        is_current_month = (target_year == today.year and target_month == today.month)
        start_of_month = date(target_year, target_month, 1)
        _, days_in_month = calendar.monthrange(target_year, target_month)
        end_of_month = date(target_year, target_month, days_in_month)
        effective_budget_limit = monthly_budget_limit

        # Days passed / remaining
        if is_current_month:
            effective_end = today
            days_passed = max(1, today.day)
            days_remaining = max(0, days_in_month - today.day)
        elif date(target_year, target_month, 1) > today:
            effective_end = end_of_month
            days_passed = 0
            days_remaining = days_in_month
        else:
            effective_end = end_of_month
            days_passed = days_in_month
            days_remaining = 0

        month_txs = all_user_txs.filter(
            is_debit=True,
            date__gte=start_of_month,
            date__lte=effective_end,
        )
        month_name = calendar.month_name[target_month]
        month_label = f"{month_name} {target_year}"
        month_key = f"{target_year:04d}-{target_month:02d}"

    total_spent_month = float(month_txs.aggregate(s=Sum('amount'))['s'] or 0.0)
    remaining_budget = max(0.0, effective_budget_limit - total_spent_month)
    percent_budget_used = round((total_spent_month / effective_budget_limit * 100), 1) if effective_budget_limit > 0 else 0.0

    daily_burn_rate_month = round(total_spent_month / max(1, days_passed), 2)
    daily_budget_allowance = round(remaining_budget / max(1, days_remaining), 2) if days_remaining > 0 else 0.0

    # Aggregate by category
    category_totals = {}
    for tx in month_txs:
        cat = tx.category or 'Other'
        category_totals[cat] = category_totals.get(cat, 0.0) + float(tx.amount)

    category_breakdown = []
    budget_alerts = []

    for cat in CATEGORIES:
        spent = round(category_totals.get(cat, 0.0), 2)
        share_weight = CATEGORY_BENCHMARK_SHARES.get(cat, 0.05)
        cat_budget = round(monthly_budget_limit * share_weight, 2)
        share_percent_used = round((spent / cat_budget * 100), 1) if cat_budget > 0 else 0.0
        pct_of_total_spend = round((spent / total_spent_month * 100), 1) if total_spent_month > 0 else 0.0

        meta = CATEGORY_METADATA.get(cat, {'icon': '🏷️', 'color': '#64748b'})

        cat_item = {
            'category': cat,
            'name': cat,
            'spent': spent,
            'budget': cat_budget,
            'percent_used': share_percent_used,
            'percent_of_total': pct_of_total_spend,
            'icon': meta['icon'],
            'color': meta['color'],
            'is_warning_80': share_percent_used >= 80.0,
            'is_exceeded_100': share_percent_used >= 100.0,
            'transaction_count': month_txs.filter(category=cat).count(),
        }
        category_breakdown.append(cat_item)

        if spent > 0:
            if share_percent_used >= 100.0:
                budget_alerts.append({
                    'id': f"alert-exceeded-{cat.lower()}",
                    'severity': 'danger',
                    'level': 100,
                    'category': cat,
                    'icon': meta['icon'],
                    'spent': spent,
                    'budget': cat_budget,
                    'percent': share_percent_used,
                    'title': f"{cat} Budget Exceeded (100%+)",
                    'message': f"You have spent ₹{spent:,.2f} on {cat}, exceeding the ₹{cat_budget:,.2f} allocated monthly budget limit ({share_percent_used}%).",
                })
            elif share_percent_used >= 80.0:
                budget_alerts.append({
                    'id': f"alert-warning-{cat.lower()}",
                    'severity': 'warning',
                    'level': 80,
                    'category': cat,
                    'icon': meta['icon'],
                    'spent': spent,
                    'budget': cat_budget,
                    'percent': share_percent_used,
                    'title': f"{cat} Approaching Budget Cap (80%+)",
                    'message': f"You have reached {share_percent_used}% of your monthly {cat} budget (₹{spent:,.2f} of ₹{cat_budget:,.2f}). Consider slowing down.",
                })

    category_breakdown.sort(key=lambda x: x['spent'], reverse=True)

    if percent_budget_used >= 100.0:
        budget_alerts.insert(0, {
            'id': 'alert-overall-exceeded',
            'severity': 'danger',
            'level': 100,
            'category': 'Total Budget',
            'icon': '🚨',
            'spent': total_spent_month,
            'budget': monthly_budget_limit,
            'percent': percent_budget_used,
            'title': 'Monthly Budget Exceeded!',
            'message': f"Total monthly expenditure (₹{total_spent_month:,.2f}) has passed your ₹{monthly_budget_limit:,.2f} limit ({percent_budget_used}% consumed).",
        })
    elif percent_budget_used >= 80.0:
        budget_alerts.insert(0, {
            'id': 'alert-overall-warning',
            'severity': 'warning',
            'level': 80,
            'category': 'Total Budget',
            'icon': '⚠️',
            'spent': total_spent_month,
            'budget': monthly_budget_limit,
            'percent': percent_budget_used,
            'title': 'Overall Budget Warning (80%+ Consumed)',
            'message': f"You have spent {percent_budget_used}% of your total semester budget (₹{total_spent_month:,.2f} / ₹{monthly_budget_limit:,.2f}) with {days_remaining} days left in the month.",
        })

    if not is_all_months:
        month_name = calendar.month_name[target_month]
        month_label = f"{month_name} {target_year}"
        month_key = f"{target_year:04d}-{target_month:02d}"

    available_months = get_available_months_for_user(user)

    return {
        'year': target_year,
        'month': 'all' if is_all_months else target_month,
        'month_key': month_key,
        'month_label': month_label,
        'is_current_month': is_current_month,
        'is_all_months': is_all_months,
        'total_spent_month': total_spent_month,
        'transaction_count': month_txs.count(),
        'category_breakdown': category_breakdown,
        'budget': {
            'monthly_limit': effective_budget_limit,
            'monthly_income': monthly_income,
            'total_spent_month': total_spent_month,
            'remaining_budget': remaining_budget,
            'percent_used': percent_budget_used,
            'days_in_month': days_in_month,
            'days_passed': days_passed,
            'days_remaining': days_remaining,
            'daily_burn_rate': daily_burn_rate_month,
            'daily_allowance_remaining': daily_budget_allowance,
        },
        'budget_alerts': budget_alerts,
        'available_months': available_months,
    }


def get_dashboard_summary(
    user: User,
    year: Any = None,
    month: Any = None,
) -> Dict[str, Any]:
    """
    Builds the complete dashboard summary payload for a student user.
    Category breakdown and monthly budget metrics respect optional year/month.
    Runway forecast and goals remain forward-looking (tied to current status).
    """
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={'college_roll_number': f'ROLL-{user.id}', 'monthly_budget_limit': 15000.0},
    )

    today = date.today()
    breakdown_data = get_category_breakdown_for_month(user, year=year, month=month)

    monthly_budget_limit = breakdown_data['budget']['monthly_limit']
    monthly_income = breakdown_data['budget']['monthly_income']
    daily_burn_rate_month = breakdown_data['budget']['daily_burn_rate']
    all_user_txs = Transaction.objects.filter(user=user, is_deleted=False, is_duplicate=False)

    # 4. Runway Summary
    try:
        runway_info = calculate_cash_flow_runway(user)
    except Exception as e:
        runway_info = {
            'runway_date': None,
            'runway_days': 30,
            'is_exhausted': False,
            'daily_burn_rate': daily_burn_rate_month or 150.0,
            'forecast_series': [],
            'error': str(e),
        }

    # 5. Goals Summary
    goals_qs = Goal.objects.filter(user=user)
    active_goals = [g for g in goals_qs if g.status == Goal.Status.ACTIVE]
    goals_summary_list = []
    for g in goals_qs[:4]:
        target = float(g.target_amount)
        saved = float(g.saved_so_far)
        pct = round((saved / target * 100), 1) if target > 0 else 0.0
        goals_summary_list.append({
            'id': g.id,
            'name': g.name,
            'target_amount': target,
            'saved_so_far': saved,
            'progress_percent': pct,
            'deadline': g.deadline.isoformat(),
            'weekly_target': g.weekly_target,
            'status': g.status,
            'is_done': g.status == Goal.Status.DONE,
        })

    try:
        goal_eval = check_goal_progress_and_suggest_cut(user)
    except Exception:
        goal_eval = {'has_active_goals': bool(active_goals), 'is_behind': False}

    # 6. Financial Health Score Summary
    try:
        health_info = get_user_financial_health_score(user, year=breakdown_data['year'], month=breakdown_data['month'])
    except Exception as e:
        health_info = {
            'health_score': 75,
            'rating': 'Good',
            'sub_scores': {'savings_rate': 28, 'budget_adherence': 24, 'volatility': 23},
            'tips': ['Keep tracking your expenses to build accurate financial score history.'],
            'error': str(e),
        }

    # 7. Verification pipeline & transaction counts
    counts = {
        'all': all_user_txs.count(),
        'auto': all_user_txs.filter(status=Transaction.ParseStatus.AUTO).count(),
        'verify': all_user_txs.filter(status=Transaction.ParseStatus.VERIFY).count(),
        'pending': all_user_txs.filter(status=Transaction.ParseStatus.PENDING).count(),
    }

    # Recent transactions (top 8)
    recent_qs = all_user_txs.order_by('-date', '-id')[:8]
    recent_transactions = []
    for t in recent_qs:
        recent_transactions.append({
            'id': t.id,
            'date': t.date.isoformat(),
            'amount': float(t.amount),
            'payee_name': t.payee_name or 'Unknown Payee',
            'upi_id': t.upi_id,
            'remark': t.remark or '',
            'category': t.category or 'Other',
            'confidence': float(t.confidence) if t.confidence is not None else None,
            'status': t.status,
            'is_debit': t.is_debit,
        })

    return {
        'user': {
            'username': user.username,
            'email': user.email,
            'college_roll_number': profile.college_roll_number,
            'monthly_budget_limit': monthly_budget_limit,
            'monthly_income': monthly_income,
            'is_onboarded': bool(profile.monthly_budget_limit and profile.monthly_budget_limit > 0),
        },
        'budget': breakdown_data['budget'],
        'category_breakdown': breakdown_data['category_breakdown'],
        'budget_alerts': breakdown_data['budget_alerts'],
        'selected_month': {
            'year': breakdown_data['year'],
            'month': breakdown_data['month'],
            'month_key': breakdown_data['month_key'],
            'month_label': breakdown_data['month_label'],
            'is_current_month': breakdown_data['is_current_month'],
        },
        'available_months': breakdown_data['available_months'],
        'runway': {
            'runway_date': runway_info.get('runway_date'),
            'runway_days': runway_info.get('runway_days'),
            'is_exhausted': runway_info.get('is_exhausted', False),
            'daily_burn_rate': runway_info.get('daily_burn_rate'),
            'current_balance': runway_info.get('current_balance'),
            'forecast_series': runway_info.get('forecast_series', [])[:35],
            'method': runway_info.get('method', 'baseline'),
        },
        'goals': {
            'items': goals_summary_list,
            'total_active': len(active_goals),
            'evaluation': goal_eval,
        },
        'health_score': health_info,
        'transactions_summary': {
            'counts': counts,
            'recent': recent_transactions,
            'needs_review_count': counts['verify'] + counts['pending'],
        },
    }
