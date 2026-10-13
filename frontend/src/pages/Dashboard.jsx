import React, { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  AreaChart,
  Area,
} from 'recharts';
import { dashboardService } from '../api';
import FinancialHealthCard from '../components/FinancialHealthCard';
import AddExpenseModal from '../components/AddExpenseModal';
import QuickExpenseBar from '../components/QuickExpenseBar';
import './Dashboard.css';

const formatMonthLabel = (mKey) => {
  if (!mKey) return '';
  if (mKey === 'all' || mKey.endsWith('-all')) {
    const yearStr = mKey.includes('-') ? mKey.split('-')[0] : '';
    return yearStr ? `All Months (${yearStr})` : 'All Months (Overall)';
  }
  const [yearStr, monthStr] = mKey.split('-');
  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];
  const mIndex = parseInt(monthStr, 10) - 1;
  const name = monthNames[mIndex] || monthStr;
  return `${name} ${yearStr}`;
};

export default function Dashboard({ userProfile, onOpenBudgetModal }) {
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dismissedAlerts, setDismissedAlerts] = useState({});
  const [categoryView, setCategoryView] = useState('pie'); // 'pie' | 'bars'
  const [isAddExpenseModalOpen, setIsAddExpenseModalOpen] = useState(false);

  // Month-wise Breakdown state
  const [selectedMonthKey, setSelectedMonthKey] = useState('');
  const [availableMonths, setAvailableMonths] = useState([]);
  const [monthBreakdownData, setMonthBreakdownData] = useState(null);
  const [isMonthLoading, setIsMonthLoading] = useState(false);

  const fetchDashboardData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const summary = await dashboardService.getSummary();
      setData(summary);

      const today = new Date();
      const currKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
      const initialKey = summary.selected_month?.month_key || currKey;
      setSelectedMonthKey((prev) => prev || initialKey);

      const serverAvailable = summary.available_months || [];
      const safeAvailable = serverAvailable.includes(initialKey)
        ? serverAvailable
        : [...serverAvailable, initialKey].sort();
      setAvailableMonths(safeAvailable.length ? safeAvailable : [initialKey]);

      setMonthBreakdownData({
        category_breakdown: summary.category_breakdown || [],
        budget: summary.budget || {},
        budget_alerts: summary.budget_alerts || [],
        total_spent_month: summary.budget?.total_spent_month || 0,
        transaction_count: (summary.category_breakdown || []).reduce((acc, c) => acc + (c.transaction_count || 0), 0),
        month_label: summary.selected_month?.month_label || formatMonthLabel(initialKey),
        month_key: initialKey,
        is_current_month: summary.selected_month?.is_current_month ?? true,
        available_months: safeAvailable,
      });
    } catch (err) {
      console.error('Failed to load dashboard summary:', err);
      setError(err?.response?.data?.error || 'Unable to connect to financial analytics service.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const handleSelectMonth = async (mKey) => {
    if (!mKey || mKey === selectedMonthKey) return;
    setSelectedMonthKey(mKey);
    setIsMonthLoading(true);
    try {
      let params = {};
      if (mKey === 'all') {
        params = { month: 'all' };
      } else if (mKey.endsWith('-all')) {
        params = { month: 'all', year: parseInt(mKey.split('-')[0], 10) };
      } else {
        const [y, m] = mKey.split('-');
        params = {
          month: parseInt(m, 10),
          year: parseInt(y, 10),
        };
      }
      const breakdown = await dashboardService.getCategoryBreakdown(params);
      setMonthBreakdownData(breakdown);
      if (breakdown.available_months && breakdown.available_months.length) {
        setAvailableMonths(breakdown.available_months);
      }
    } catch (err) {
      console.error('Failed to load month category breakdown:', err);
    } finally {
      setIsMonthLoading(false);
    }
  };

  const handleDismissAlert = (alertId) => {
    setDismissedAlerts((prev) => ({ ...prev, [alertId]: true }));
  };

  if (loading) {
    return (
      <div className="dash-loading" id="dashboard-loading">
        <div className="dash-spinner"></div>
        <p style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>
          Synchronizing student transactions, runway projection, and budget limits...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dash-empty-state" id="dashboard-error">
        <span className="dash-empty-icon">⚠️</span>
        <h3 style={{ color: '#f87171', margin: 0 }}>Dashboard Service Unavailable</h3>
        <p style={{ color: 'var(--text-secondary)', maxWidth: 460 }}>{error}</p>
        <button
          type="button"
          onClick={fetchDashboardData}
          className="btn-primary"
          id="btn-retry-dashboard"
        >
          🔄 Try Again
        </button>
      </div>
    );
  }

  const {
    budget = {},
    category_breakdown = [],
    budget_alerts = [],
    runway = {},
    goals = {},
    health_score = {},
    transactions_summary = {},
  } = data || {};

  const monthlyLimit = budget.monthly_limit || 15000.0;
  const spentThisMonth = budget.total_spent_month || 0.0;
  const remaining = budget.remaining_budget || 0.0;
  const pctUsed = budget.percent_used || 0.0;
  const daysLeft = budget.days_remaining !== undefined ? budget.days_remaining : 20;
  const dailyBurn = budget.daily_burn_rate || 0.0;
  const dailyAllowance = budget.daily_allowance_remaining || 0.0;

  // Filter out dismissed alerts
  const visibleAlerts = budget_alerts.filter((a) => !dismissedAlerts[a.id]);

  // Active month Breakdown Data
  const todayDate = new Date();
  const currentMonthKey = `${todayDate.getFullYear()}-${String(todayDate.getMonth() + 1).padStart(2, '0')}`;

  const activeMonthData = monthBreakdownData || {
    category_breakdown: category_breakdown,
    budget: budget,
    budget_alerts: budget_alerts,
    total_spent_month: spentThisMonth,
    transaction_count: 0,
    month_label: data?.selected_month?.month_label || formatMonthLabel(selectedMonthKey || currentMonthKey),
    month_key: selectedMonthKey || currentMonthKey,
    is_current_month: true,
  };

  const activeCategoryBreakdown = activeMonthData.category_breakdown || [];
  const activeMonthBudget = activeMonthData.budget || {};
  const activeMonthLabel = activeMonthData.month_label || formatMonthLabel(selectedMonthKey || currentMonthKey);
  const activeMonthSpent = activeMonthData.total_spent_month ?? (activeMonthBudget.total_spent_month || 0);
  const activeMonthTxCount = activeMonthData.transaction_count ?? 0;
  const isSelectedMonthCurrent = activeMonthData.is_current_month ?? (selectedMonthKey === currentMonthKey);
  const activeMonthBudgetLimit = activeMonthBudget.monthly_limit || monthlyLimit;
  const activeMonthPercentUsed = activeMonthBudget.percent_used || (activeMonthBudgetLimit > 0 ? Math.round((activeMonthSpent / activeMonthBudgetLimit) * 100) : 0);

  // Group available months by year
  const monthsByYear = availableMonths.reduce((acc, mKey) => {
    if (mKey.includes('-') && !mKey.endsWith('-all')) {
      const [yr] = mKey.split('-');
      if (!acc[yr]) acc[yr] = [];
      acc[yr].push(mKey);
    }
    return acc;
  }, {});

  // Stepper boundary checks
  const currentIndex = availableMonths.indexOf(selectedMonthKey);
  const isPrevDisabled = currentIndex <= 0 && selectedMonthKey !== 'all' && !selectedMonthKey.endsWith('-all');
  const isNextDisabled = (currentIndex === -1 || currentIndex >= availableMonths.length - 1) && selectedMonthKey !== 'all' && !selectedMonthKey.endsWith('-all');

  const handlePrevMonth = () => {
    if (selectedMonthKey === 'all' || selectedMonthKey.endsWith('-all')) {
      handleSelectMonth(currentMonthKey);
      return;
    }
    if (currentIndex > 0) {
      handleSelectMonth(availableMonths[currentIndex - 1]);
    }
  };

  const handleNextMonth = () => {
    if (selectedMonthKey === 'all' || selectedMonthKey.endsWith('-all')) {
      handleSelectMonth(currentMonthKey);
      return;
    }
    if (currentIndex >= 0 && currentIndex < availableMonths.length - 1) {
      handleSelectMonth(availableMonths[currentIndex + 1]);
    }
  };

  // Pie chart data scoped to active month
  const pieData = activeCategoryBreakdown
    .filter((c) => c.spent > 0)
    .map((c) => ({
      name: c.category,
      value: c.spent,
      color: c.color,
      icon: c.icon,
    }));

  // Bar chart data comparing spent vs budget for active month
  const barData = activeCategoryBreakdown.map((c) => ({
    name: c.category.length > 10 ? c.category.slice(0, 9) + '…' : c.category,
    fullName: c.category,
    Spent: c.spent,
    Budget: c.budget,
    pctUsed: c.percent_used,
    color: c.color,
  }));

  // Clean runway forecast chart points (tied to current month)
  const runwaySeries = (runway.forecast_series || []).slice(0, 30).map((pt, idx) => ({
    day: pt.date ? pt.date.slice(5) : `Day ${idx + 1}`,
    actual: pt.actual_spend !== null && pt.actual_spend !== undefined ? pt.actual_spend : null,
    forecast: pt.predicted_spend !== null && pt.predicted_spend !== undefined ? pt.predicted_spend : null,
    balance: pt.projected_balance !== null && pt.projected_balance !== undefined ? pt.projected_balance : null,
  }));

  const activeGoals = goals.items || [];
  const goalEvaluation = goals.evaluation || {};
  const recentTxs = transactions_summary.recent || [];
  const needsReviewCount = transactions_summary.needs_review_count || 0;

  return (
    <div className="dashboard-container" id="unified-dashboard">
      {/* ── Page Header ── */}
      <div className="dashboard-header">
        <div className="dashboard-greeting">
          <h2 className="dashboard-title">
            Welcome back, {userProfile?.username || data?.user?.username || 'Student'}! 👋
          </h2>
          <p className="dashboard-subtitle">
            Roll No: <strong style={{ color: '#fff' }}>{userProfile?.college_roll_number || data?.user?.college_roll_number || 'N/A'}</strong>
            <span>•</span>
            Monthly Budget Cap: <strong style={{ color: '#a5b4fc' }}>₹{monthlyLimit.toLocaleString()}</strong>
            <span>•</span>
            <span>{daysLeft} days remaining this month</span>
          </p>
        </div>

        <div className="dashboard-actions">
          <button
            type="button"
            onClick={() => setIsAddExpenseModalOpen(true)}
            className="btn-primary"
            id="btn-dash-add-expense"
            style={{ background: 'linear-gradient(135deg, #10b981, #059669)', border: 'none', color: '#fff', boxShadow: '0 4px 12px rgba(16, 185, 129, 0.35)' }}
          >
            ➕ Add Expense
          </button>
          <button
            type="button"
            onClick={onOpenBudgetModal}
            className="btn-secondary"
            id="btn-adjust-budget-limit"
            title="Adjust monthly budget limit"
          >
            ⚙️ Edit Budget Limit
          </button>
          <Link to="/upload" className="btn-primary" id="btn-dash-upload-statement">
            📄 Upload Statement
          </Link>
        </div>
      </div>

      {/* ── Quick Expense Logging ── */}
      <QuickExpenseBar
        onExpenseAdded={fetchDashboardData}
        onOpenFullModal={() => setIsAddExpenseModalOpen(true)}
      />

      {/* ── Active Budget Alerts (80% and 100% threshold crossings) ── */}
      {visibleAlerts.length > 0 && (
        <div className="alerts-stack" id="budget-alerts-stack">
          {visibleAlerts.map((alert) => (
            <div
              key={alert.id}
              className={`budget-alert-card ${alert.level >= 100 ? 'budget-alert-danger' : 'budget-alert-warning'}`}
              id={alert.id}
            >
              <div className="alert-left">
                <div className="alert-icon-box">{alert.icon || (alert.level >= 100 ? '🚨' : '⚠️')}</div>
                <div>
                  <h4 className="alert-title">{alert.title}</h4>
                  <p className="alert-msg">{alert.message}</p>
                </div>
              </div>
              <div className="alert-right">
                <span className="alert-badge">
                  {alert.percent}% {alert.level >= 100 ? 'EXCEEDED' : 'OF BUDGET'}
                </span>
                <button
                  type="button"
                  className="alert-close-btn"
                  onClick={() => handleDismissAlert(alert.id)}
                  title="Dismiss alert"
                  aria-label="Dismiss alert"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Needs Review Banner ── */}
      {needsReviewCount > 0 && (
        <div
          style={{
            background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.16) 0%, rgba(79, 70, 229, 0.08) 100%)',
            border: '1px solid rgba(129, 140, 248, 0.4)',
            borderRadius: '14px',
            padding: '0.9rem 1.25rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            flexWrap: 'wrap',
          }}
          id="needs-review-banner"
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '1.4rem' }}>🔍</span>
            <div>
              <strong style={{ color: '#f8fafc', fontSize: '0.95rem' }}>
                {needsReviewCount} transaction{needsReviewCount > 1 ? 's' : ''} require your categorization review
              </strong>
              <p style={{ margin: '0.15rem 0 0 0', color: '#cbd5e1', fontSize: '0.85rem' }}>
                Verify payee categories to keep machine learning accuracy and budget analytics 100% precise.
              </p>
            </div>
          </div>
          <Link
            to="/transactions"
            style={{
              background: '#4f46e5',
              color: '#ffffff',
              padding: '0.5rem 1rem',
              borderRadius: '8px',
              fontWeight: 600,
              fontSize: '0.85rem',
              textDecoration: 'none',
              boxShadow: '0 2px 8px rgba(79, 70, 229, 0.35)',
            }}
            id="btn-goto-review-txs"
          >
            Review Transactions →
          </Link>
        </div>
      )}

      {/* ── Metric Cards Row: Budget vs Actual This Month ── */}
      <section className="dashboard-metrics" id="budget-kpis-grid">
        {/* Metric 1: Monthly Budget Limit */}
        <div className="kpi-card" id="kpi-monthly-limit">
          <div className="kpi-header">
            <span className="kpi-label">MONTHLY BUDGET CAP</span>
            <div className="kpi-icon-wrap" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#818cf8' }}>
              💳
            </div>
          </div>
          <div className="kpi-value">₹{monthlyLimit.toLocaleString()}</div>
          <div className="kpi-footer">
            <span>Allocated spending limit</span>
            <button
              type="button"
              onClick={onOpenBudgetModal}
              style={{
                background: 'none',
                border: 'none',
                color: '#818cf8',
                cursor: 'pointer',
                fontSize: '0.78rem',
                fontWeight: 600,
                textDecoration: 'underline',
                padding: 0,
              }}
            >
              Adjust Cap
            </button>
          </div>
        </div>

        {/* Metric 2: Actual Spent This Month */}
        <div className="kpi-card" id="kpi-spent-this-month">
          <div className="kpi-header">
            <span className="kpi-label">TOTAL MONTH SPEND</span>
            <div
              className="kpi-icon-wrap"
              style={{
                background: pctUsed >= 100 ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                color: pctUsed >= 100 ? '#f87171' : '#fbbf24',
              }}
            >
              📉
            </div>
          </div>
          <div className="kpi-value">₹{spentThisMonth.toLocaleString()}</div>
          <div className="kpi-progress-bar">
            <div
              className="kpi-progress-fill"
              style={{
                width: `${Math.min(100, pctUsed)}%`,
                background:
                  pctUsed >= 100
                    ? 'linear-gradient(90deg, #ef4444, #b91c1c)'
                    : pctUsed >= 80
                    ? 'linear-gradient(90deg, #f59e0b, #d97706)'
                    : 'linear-gradient(90deg, #4f46e5, #06b6d4)',
              }}
            ></div>
          </div>
          <div className="kpi-footer">
            <span style={{ color: pctUsed >= 80 ? '#f87171' : '#34d399', fontWeight: 600 }}>
              {pctUsed}% consumed
            </span>
            <span>{daysLeft} days remaining</span>
          </div>
        </div>

        {/* Metric 3: Remaining Balance */}
        <div className="kpi-card" id="kpi-remaining-budget">
          <div className="kpi-header">
            <span className="kpi-label">REMAINING ALLOWANCE</span>
            <div className="kpi-icon-wrap" style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#34d399' }}>
              💰
            </div>
          </div>
          <div className="kpi-value" style={{ color: remaining <= 0 ? '#f87171' : '#34d399' }}>
            ₹{remaining.toLocaleString()}
          </div>
          <div className="kpi-footer">
            <span>₹{dailyAllowance.toLocaleString()}/day allowance</span>
            <span style={{ color: remaining > 0 ? '#34d399' : '#f87171' }}>
              {remaining > 0 ? 'On Track' : 'Exceeded'}
            </span>
          </div>
        </div>

        {/* Metric 4: Daily Burn Rate */}
        <div className="kpi-card" id="kpi-burn-rate">
          <div className="kpi-header">
            <span className="kpi-label">DAILY BURN RATE</span>
            <div className="kpi-icon-wrap" style={{ background: 'rgba(6, 182, 212, 0.15)', color: '#22d3ee' }}>
              ⚡
            </div>
          </div>
          <div className="kpi-value">₹{dailyBurn.toLocaleString()}</div>
          <div className="kpi-footer">
            <span>Average outflow per day</span>
            <span style={{ color: '#94a3b8' }}>October 2026</span>
          </div>
        </div>
      </section>

      {/* ── Row: Category Breakdown & Spending Distribution ── */}
      <section className="dash-grid-2">
        {/* Category Breakdown Chart Card with Month Selector */}
        <div className="dash-panel" id="category-breakdown-card">
          <div className="panel-header">
            <h3 className="panel-title">
              <span>📊</span> Category Spending Breakdown
            </h3>
          </div>

          {/* Month Selector Toolbar: Stepper & Dropdown */}
          <div className="category-panel-toolbar" id="category-month-selector-toolbar">
            <div className="month-stepper-control" id="month-stepper-control">
              <button
                type="button"
                className="month-stepper-nav-btn"
                id="btn-prev-month"
                disabled={isPrevDisabled || isMonthLoading}
                onClick={handlePrevMonth}
                title={isPrevDisabled ? "Earliest month with transaction data" : "Navigate to previous month"}
                aria-label="Previous Month"
              >
                ◀
              </button>

              <div className="month-stepper-label-wrap">
                <select
                  id="select-breakdown-month"
                  className="month-stepper-select"
                  value={selectedMonthKey}
                  onChange={(e) => handleSelectMonth(e.target.value)}
                  disabled={isMonthLoading}
                  aria-label="Select spending month"
                >
                  <optgroup label="Summary Views">
                    <option value={`${todayDate.getFullYear()}-all`}>
                      All Months ({todayDate.getFullYear()})
                    </option>
                    <option value="all">All Months (Overall)</option>
                  </optgroup>
                  {Object.keys(monthsByYear)
                    .sort((a, b) => b - a)
                    .map((yr) => (
                      <optgroup key={yr} label={`Year ${yr}`}>
                        {monthsByYear[yr].map((mKey) => (
                          <option key={mKey} value={mKey}>
                            {formatMonthLabel(mKey)} {mKey === currentMonthKey ? '• Current' : ''}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                </select>
                {selectedMonthKey === 'all' || selectedMonthKey.endsWith('-all') ? (
                  <span className="month-badge-pill badge-all">All Months</span>
                ) : isSelectedMonthCurrent ? (
                  <span className="month-badge-pill badge-current">Current Month</span>
                ) : (
                  <span className="month-badge-pill badge-past">
                    {selectedMonthKey > currentMonthKey ? 'Upcoming Month' : 'Past Month'}
                  </span>
                )}
              </div>

              <button
                type="button"
                className="month-stepper-nav-btn"
                id="btn-next-month"
                disabled={isNextDisabled || isMonthLoading}
                onClick={handleNextMonth}
                title={isNextDisabled ? "Latest month with transaction data" : "Navigate to next month"}
                aria-label="Next Month"
              >
                ▶
              </button>
            </div>

            <div className="segmented-control">
              <button
                type="button"
                className={`segmented-btn ${categoryView === 'pie' ? 'active' : ''}`}
                onClick={() => setCategoryView('pie')}
                id="toggle-cat-pie"
              >
                Pie
              </button>
              <button
                type="button"
                className={`segmented-btn ${categoryView === 'bars' ? 'active' : ''}`}
                onClick={() => setCategoryView('bars')}
                id="toggle-cat-bars"
              >
                Budget vs Actual
              </button>
            </div>
          </div>

          {/* Scoped Month Figures: Total Outflow & Budget Consumption */}
          <div className="month-stats-banner" id="month-stats-banner">
            <div className="month-stat-item">
              <span className="month-stat-label">Month Outflow</span>
              <span className="month-stat-val">₹{activeMonthSpent.toLocaleString()}</span>
            </div>
            <div className="month-stat-item">
              <span className="month-stat-label">Monthly Cap</span>
              <span className="month-stat-val">₹{Number(activeMonthBudgetLimit).toLocaleString()}</span>
            </div>
            <div className="month-stat-item">
              <span className="month-stat-label">Budget Consumed</span>
              <span className={`month-stat-val ${activeMonthPercentUsed >= 100 ? 'stat-danger' : activeMonthPercentUsed >= 80 ? 'stat-warning' : 'stat-success'}`}>
                {activeMonthPercentUsed}%
              </span>
            </div>
            <div className="month-stat-item">
              <span className="month-stat-label">Transactions</span>
              <span className="month-stat-val">{activeMonthTxCount}</span>
            </div>
          </div>

          {isMonthLoading ? (
            <div className="month-loading-overlay" id="month-loading-overlay">
              <div className="month-spinner-mini"></div>
              <span>Updating {activeMonthLabel} category breakdown...</span>
            </div>
          ) : pieData.length === 0 ? (
            <div className="dash-empty-state" id="category-month-empty-state" style={{ minHeight: 260 }}>
              <span style={{ fontSize: '2.5rem' }}>📭</span>
              <h4 style={{ margin: '0.4rem 0 0.2rem', color: '#f8fafc', fontSize: '1.05rem', fontWeight: 700 }}>
                No transactions recorded for this month
              </h4>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.86rem', maxWidth: 380, textAlign: 'center', margin: 0 }}>
                There are no active expenses recorded for {activeMonthLabel}. Pick another month or upload a statement.
              </p>
              {isSelectedMonthCurrent && (
                <Link to="/upload" className="btn-secondary" style={{ padding: '0.4rem 0.9rem', fontSize: '0.85rem', marginTop: '0.4rem' }}>
                  Upload Bank Statement
                </Link>
              )}
            </div>
          ) : categoryView === 'pie' ? (
            <div style={{ width: '100%', height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={95}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1e293b',
                      borderColor: 'rgba(255,255,255,0.12)',
                      borderRadius: '10px',
                      color: '#fff',
                    }}
                    formatter={(val) => [`₹${Number(val).toLocaleString()}`, 'Spent']}
                  />
                  <Legend
                    verticalAlign="bottom"
                    iconType="circle"
                    wrapperStyle={{ fontSize: '0.78rem', paddingTop: '10px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div style={{ width: '100%', height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} />
                  <YAxis stroke="#64748b" fontSize={11} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1e293b',
                      borderColor: 'rgba(255,255,255,0.12)',
                      borderRadius: '10px',
                      color: '#fff',
                    }}
                    formatter={(val, name) => [`₹${Number(val).toLocaleString()}`, name]}
                  />
                  <Legend wrapperStyle={{ fontSize: '0.78rem', paddingTop: '8px' }} />
                  <Bar dataKey="Spent" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Budget" fill="rgba(255,255,255,0.18)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Category Share List with 80% / 100% threshold indicators */}
          <div className="category-bars-list">
            {activeCategoryBreakdown
              .filter((c) => c.spent > 0 || c.budget > 0)
              .slice(0, 4)
              .map((c) => (
                <div key={c.category} className="cat-bar-item">
                  <div className="cat-bar-meta">
                    <span className="cat-bar-left">
                      <span>{c.icon}</span>
                      <span>{c.category}</span>
                      {c.is_exceeded_100 && (
                        <span style={{ fontSize: '0.7rem', color: '#f87171', fontWeight: 700 }}>
                          [100%+ EXCEEDED]
                        </span>
                      )}
                      {!c.is_exceeded_100 && c.is_warning_80 && (
                        <span style={{ fontSize: '0.7rem', color: '#fbbf24', fontWeight: 700 }}>
                          [80%+ WARNING]
                        </span>
                      )}
                    </span>
                    <span className="cat-bar-right">
                      <strong style={{ color: '#f8fafc' }}>₹{c.spent.toLocaleString()}</strong>
                      <span>/ ₹{c.budget.toLocaleString()}</span>
                      <span style={{ color: c.is_exceeded_100 ? '#f87171' : c.is_warning_80 ? '#fbbf24' : '#94a3b8' }}>
                        ({c.percent_used}%)
                      </span>
                    </span>
                  </div>
                  <div className="cat-bar-track">
                    <div
                      className="cat-bar-fill"
                      style={{
                        width: `${Math.min(100, c.percent_used)}%`,
                        backgroundColor: c.is_exceeded_100 ? '#ef4444' : c.is_warning_80 ? '#f59e0b' : c.color,
                      }}
                    ></div>
                    {/* Visual 80% benchmark mark line */}
                    <div className="cat-bar-threshold" style={{ left: '80%' }} title="80% budget alert mark"></div>
                  </div>
                </div>
              ))}
          </div>
        </div>

        {/* Cash-Flow Runway Projection Card */}
        <div className="dash-panel" id="runway-forecast-card">
          <div className="panel-header">
            <h3 className="panel-title">
              <span>✈️</span> Cash-Flow Runway
            </h3>
            <Link
              to="/runway"
              className="btn-secondary"
              style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem' }}
              id="link-try-whatif"
            >
              Try What-If Simulator →
            </Link>
          </div>

          <div className="runway-summary-badge">
            <div style={{ fontSize: '1.8rem' }}>📅</div>
            <div>
              <div className="runway-date-pill">
                Runway: {runway.runway_date ? `${runway.runway_date} (${runway.runway_days} days)` : 'Healthy (30+ days)'}
              </div>
              <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.82rem', color: '#cbd5e1' }}>
                At current outflow (₹{dailyBurn.toLocaleString()}/day), projected funds are mapped for semester stability.
              </p>
            </div>
          </div>

          <div style={{ width: '100%', height: 230 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={runwaySeries} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="runwayGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.5} />
                    <stop offset="95%" stopColor="#4f46e5" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="day" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    borderColor: 'rgba(255,255,255,0.12)',
                    borderRadius: '8px',
                    color: '#fff',
                  }}
                  formatter={(val, name) => [`₹${Number(val).toLocaleString()}`, name]}
                />
                <Area
                  type="monotone"
                  dataKey="forecast"
                  name="Forecasted Outflow"
                  stroke="#818cf8"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#runwayGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {/* ── Row: Goals Progress & Financial Health Score ── */}
      <section className="dash-grid-2">
        {/* Goals Progress Card */}
        <div className="dash-panel" id="goals-progress-card">
          <div className="panel-header">
            <h3 className="panel-title">
              <span>🎯</span> Savings Goals Progress
            </h3>
            <Link
              to="/goals"
              className="btn-secondary"
              style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem' }}
              id="link-manage-goals"
            >
              Manage Goals →
            </Link>
          </div>

          {/* Goal Velocity Alert */}
          {goalEvaluation.has_active_goals && goalEvaluation.is_behind && (
            <div
              style={{
                background: 'rgba(239, 68, 68, 0.12)',
                border: '1px solid rgba(239, 68, 68, 0.35)',
                borderRadius: '12px',
                padding: '0.75rem 1rem',
                marginBottom: '1rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '0.75rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <span style={{ fontSize: '1.2rem' }}>⚠️</span>
                <span style={{ fontSize: '0.82rem', color: '#fca5a5' }}>
                  Falling behind savings rate by ₹{goalEvaluation.weekly_deficit?.toLocaleString()}/wk!
                </span>
              </div>
              <Link
                to="/goals"
                style={{
                  color: '#fff',
                  background: '#ef4444',
                  padding: '0.3rem 0.65rem',
                  borderRadius: '6px',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  textDecoration: 'none',
                }}
              >
                What to Cut?
              </Link>
            </div>
          )}

          {activeGoals.length === 0 ? (
            <div className="dash-empty-state" style={{ minHeight: 180 }}>
              <span style={{ fontSize: '2.2rem' }}>🎯</span>
              <p style={{ color: 'var(--text-muted)' }}>No savings goals created yet.</p>
              <Link to="/goals" className="btn-primary" style={{ padding: '0.45rem 1rem', fontSize: '0.82rem' }}>
                + Set a Savings Goal
              </Link>
            </div>
          ) : (
            <div className="goals-list-mini">
              {activeGoals.map((g) => (
                <div key={g.id} className="goal-card-mini">
                  <div className="goal-mini-header">
                    <span className="goal-mini-title">{g.name}</span>
                    <span className="goal-mini-stats">
                      ₹{g.saved_so_far.toLocaleString()} / ₹{g.target_amount.toLocaleString()}
                    </span>
                  </div>
                  <div className="kpi-progress-bar">
                    <div
                      className="kpi-progress-fill"
                      style={{
                        width: `${Math.min(100, g.progress_percent)}%`,
                        background:
                          g.progress_percent >= 100
                            ? 'linear-gradient(90deg, #10b981, #059669)'
                            : 'linear-gradient(90deg, #6366f1, #38bdf8)',
                      }}
                    ></div>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', color: '#94a3b8' }}>
                    <span>Target: {g.deadline}</span>
                    <span style={{ color: '#a5b4fc', fontWeight: 600 }}>
                      ₹{g.weekly_target.toLocaleString()}/wk needed
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Financial Health Score Gauge & Tips Card */}
        <div id="financial-health-card-wrap">
          <FinancialHealthCard />
        </div>
      </section>

      {/* ── Recent Transactions Ledger ── */}
      <section className="dash-panel" id="recent-transactions-panel">
        <div className="panel-header">
          <h3 className="panel-title">
            <span>🧾</span> Recent Campus Transactions
          </h3>
          <Link
            to="/transactions"
            className="btn-secondary"
            style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem' }}
            id="link-view-all-txs"
          >
            View All Transactions →
          </Link>
        </div>

        {recentTxs.length === 0 ? (
          <div className="dash-empty-state" style={{ minHeight: 180 }}>
            <span style={{ fontSize: '2.5rem' }}>💳</span>
            <p style={{ color: 'var(--text-muted)' }}>No transactions recorded yet.</p>
            <Link to="/upload" className="btn-primary" style={{ padding: '0.5rem 1.1rem', fontSize: '0.85rem' }}>
              Upload Bank/UPI Statement
            </Link>
          </div>
        ) : (
          <div className="tx-table-wrap">
            <table className="tx-table-mini">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Payee / Description</th>
                  <th>Category</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Amount</th>
                </tr>
              </thead>
              <tbody>
                {recentTxs.map((tx) => (
                  <tr key={tx.id}>
                    <td style={{ color: 'var(--text-secondary)' }}>{tx.date}</td>
                    <td>
                      <div className="tx-payee-cell">
                        <span className="tx-payee-name">{tx.payee_name}</span>
                        {tx.remark && tx.remark !== tx.payee_name && (
                          <span className="tx-remark">{tx.remark}</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span
                        style={{
                          background: 'rgba(99, 102, 241, 0.15)',
                          color: '#818cf8',
                          padding: '0.2rem 0.55rem',
                          borderRadius: '6px',
                          fontSize: '0.78rem',
                          fontWeight: 600,
                        }}
                      >
                        {tx.category}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`status-badge-chip ${
                          tx.status === 'auto'
                            ? 'status-chip-auto'
                            : tx.status === 'verify'
                            ? 'status-chip-verify'
                            : 'status-chip-pending'
                        }`}
                      >
                        {tx.status}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right', fontWeight: 700, color: '#f8fafc' }}>
                      -₹{tx.amount.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Add Expense Modal ── */}
      <AddExpenseModal
        isOpen={isAddExpenseModalOpen}
        onClose={() => setIsAddExpenseModalOpen(false)}
        onExpenseAdded={fetchDashboardData}
      />
    </div>
  );
}
