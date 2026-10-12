import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import { planningService } from '../api';
import './Runway.css';

const CATEGORIES_LIST = [
  { name: 'Food', icon: '🍔', color: '#f59e0b', maxReduce: 70 },
  { name: 'Entertainment', icon: '🎬', color: '#f97316', maxReduce: 80 },
  { name: 'Subscriptions', icon: '📺', color: '#8b5cf6', maxReduce: 80 },
  { name: 'Groceries/Shopping', icon: '🛒', color: '#10b981', maxReduce: 60 },
  { name: 'Travel', icon: '🚗', color: '#3b82f6', maxReduce: 70 },
  { name: 'Friend/Split', icon: '👥', color: '#ec4899', maxReduce: 70 },
  { name: 'Academics', icon: '📚', color: '#06b6d4', maxReduce: 50 },
  { name: 'Stationery', icon: '✏️', color: '#14b8a6', maxReduce: 50 },
  { name: 'Utilities', icon: '💡', color: '#eab308', maxReduce: 40 },
  { name: 'Rent/Hostel', icon: '🏠', color: '#ef4444', maxReduce: 30 },
  { name: 'Other', icon: '🏷️', color: '#64748b', maxReduce: 60 },
];

export default function Runway() {
  const [balance, setBalance] = useState('');
  const [baselineData, setBaselineData] = useState(null);
  const [whatIfData, setWhatIfData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState('');

  // Slider adjustments state: { "Food": 0, "Entertainment": 0, ... }
  const [adjustments, setAdjustments] = useState({
    Food: 0,
    Entertainment: 0,
    Subscriptions: 0,
    'Groceries/Shopping': 0,
    Travel: 0,
    'Friend/Split': 0,
    Academics: 0,
    Stationery: 0,
    Utilities: 0,
    'Rent/Hostel': 0,
    Other: 0,
  });

  const debounceTimerRef = useRef(null);

  // Initial fetch of baseline runway
  const fetchBaseline = useCallback(async (balOverride) => {
    setLoading(true);
    setError('');
    try {
      const data = await planningService.getRunway(balOverride);
      setBaselineData(data);
      if (balOverride === undefined || balOverride === null) {
        setBalance(data.current_balance !== undefined ? String(data.current_balance) : '10000');
      }
    } catch (err) {
      setError(err?.response?.data?.error || 'Failed to load forecast data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBaseline();
  }, [fetchBaseline]);

  // Live simulation trigger when sliders or balance change
  const runSimulation = useCallback(
    async (currentAdjustments, balValue) => {
      const hasAnyAdjustment = Object.values(currentAdjustments).some((v) => v > 0);
      if (!hasAnyAdjustment) {
        setWhatIfData(null);
        return;
      }

      setSimulating(true);
      try {
        const payload = {
          adjustments: currentAdjustments,
          current_balance: balValue ? parseFloat(balValue) : undefined,
        };
        const res = await planningService.simulateWhatIf(payload);
        setWhatIfData(res);
      } catch (err) {
        console.error('What-if simulation error:', err);
      } finally {
        setSimulating(false);
      }
    },
    []
  );

  const handleSliderChange = (catName, value) => {
    const val = parseInt(value, 10) || 0;
    const nextAdjustments = { ...adjustments, [catName]: val };
    setAdjustments(nextAdjustments);

    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      runSimulation(nextAdjustments, balance);
    }, 280);
  };

  const handleBalanceChange = (e) => {
    const newBal = e.target.value;
    setBalance(newBal);

    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      fetchBaseline(newBal);
      const hasAnyAdjustment = Object.values(adjustments).some((v) => v > 0);
      if (hasAnyAdjustment) {
        runSimulation(adjustments, newBal);
      }
    }, 400);
  };

  const handleResetSliders = () => {
    const reset = {
      Food: 0,
      Entertainment: 0,
      Subscriptions: 0,
      'Groceries/Shopping': 0,
      Travel: 0,
      'Friend/Split': 0,
      Academics: 0,
      'Rent/Hostel': 0,
      Other: 0,
    };
    setAdjustments(reset);
    setWhatIfData(null);
  };

  // Combine chart series (baseline forecast trajectory vs what-if trajectory)
  const chartData = useMemo(() => {
    if (!baselineData) return [];

    const baseSeries = baselineData.forecast_series || [];
    const whatIfSeries = whatIfData?.adjusted_forecast_series || [];
    const whatIfMap = new Map();
    whatIfSeries.forEach((pt) => {
      whatIfMap.set(pt.date, pt);
    });

    return baseSeries.map((item) => {
      const match = whatIfMap.get(item.date);
      return {
        date: item.date.slice(5), // MM-DD for clean axis
        fullDate: item.date,
        actual: item.actual,
        forecast: item.forecast,
        balance_remaining: item.balance_remaining,
        adjusted_balance: match?.balance_remaining ?? null,
        adjusted_spend: match?.daily_spend ?? null,
      };
    });
  }, [baselineData, whatIfData]);

  // Active metrics: adjusted if what-if is active, else baseline
  const activeRunwayDate = whatIfData
    ? whatIfData.adjusted_runway_date
    : baselineData?.runway_date;
  const activeRunwayDays = whatIfData
    ? whatIfData.adjusted_runway_days
    : baselineData?.runway_days;
  const daysSaved = whatIfData?.days_saved || 0;
  const moneySaved = whatIfData?.money_saved_30d || 0;
  const burnRate = whatIfData
    ? whatIfData.adjusted_daily_burn
    : baselineData?.daily_burn_rate || 0;

  const totalAdjustedPercent = whatIfData?.total_reduction_percent || 0;

  return (
    <div className="runway-page">
      {/* Page Header */}
      <div className="runway-header">
        <div>
          <div className="header-tag-row">
            <h1 className="runway-title">Cash-Flow Runway & What-If Simulator</h1>
            <span
              className={`model-tag ${
                baselineData?.method === 'baseline_average'
                  ? 'model-tag-cold'
                  : 'model-tag-ml'
              }`}
            >
              {baselineData?.method === 'arima'
                ? '🤖 ARIMA Time-Series'
                : baselineData?.method === 'prophet'
                ? '🔮 Prophet Forecast'
                : '📊 Baseline Average (Cold Start)'}
            </span>
          </div>
          <p className="runway-subtitle">
            Forecast your spending trajectory over the next 30 days and discover exactly when funds
            will deplete. Test real-time spending cuts with the interactive simulator below.
          </p>
        </div>
      </div>

      {/* Top Metrics Cards Grid */}
      <div className="runway-metrics-grid">
        {/* Balance Card */}
        <div className="runway-metric-card glass-panel">
          <div className="metric-header">
            <span className="metric-icon">💰</span>
            <span className="metric-label">Current Balance</span>
          </div>
          <div className="balance-input-wrapper">
            <span className="currency-prefix">₹</span>
            <input
              type="number"
              className="balance-input"
              value={balance}
              onChange={handleBalanceChange}
              placeholder="10000"
              id="input-current-balance"
            />
          </div>
          <span className="metric-hint">Enter your actual balance or keep inferred estimate</span>
        </div>

        {/* Burn Rate Card */}
        <div className="runway-metric-card glass-panel">
          <div className="metric-header">
            <span className="metric-icon">🔥</span>
            <span className="metric-label">Daily Burn Rate</span>
          </div>
          <div className="metric-value">
            ₹{burnRate ? burnRate.toFixed(0) : '0'}
            <span className="unit-label">/ day</span>
          </div>
          <span className="metric-hint">
            {whatIfData ? `Reduced from ₹${baselineData?.daily_burn_rate} / day` : 'Average forecasted burn'}
          </span>
        </div>

        {/* Runway Date Card */}
        <div className={`runway-metric-card glass-panel ${daysSaved > 0 ? 'card-highlight' : ''}`}>
          <div className="metric-header">
            <span className="metric-icon">⏳</span>
            <span className="metric-label">Funds Deplete On</span>
            {daysSaved > 0 && (
              <span className="saved-badge">+{daysSaved} days!</span>
            )}
          </div>
          <div className="metric-value date-value">
            {activeRunwayDate
              ? new Date(activeRunwayDate).toLocaleDateString('en-IN', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                })
              : 'Beyond 30 Days'}
          </div>
          <span className="metric-hint">
            {activeRunwayDays !== null ? (
              <strong>{activeRunwayDays} days of runway remaining</strong>
            ) : (
              'Funds safely last past forecast window'
            )}
          </span>
        </div>

        {/* What-If Savings Card */}
        <div className="runway-metric-card glass-panel">
          <div className="metric-header">
            <span className="metric-icon">✨</span>
            <span className="metric-label">What-If Savings</span>
          </div>
          <div className="metric-value" style={{ color: daysSaved > 0 ? '#34d399' : '#94a3b8' }}>
            {moneySaved > 0 ? `+₹${moneySaved.toFixed(0)}` : '₹0'}
          </div>
          <span className="metric-hint">
            {totalAdjustedPercent > 0
              ? `${totalAdjustedPercent}% cut across targeted categories`
              : 'Adjust sliders to simulate cuts'}
          </span>
        </div>
      </div>

      {/* Main Content Layout: Chart + What-If Panel */}
      <div className="runway-layout">
        {/* Left Side: Chart Container */}
        <div className="chart-section glass-panel">
          <div className="chart-header">
            <div>
              <h3 className="section-title">30-Day Cash-Flow Depletion Trajectory</h3>
              <p className="section-desc">
                Historical daily spend (solid blue), projected remaining balance (cyan), and what-if
                trajectory (green).
              </p>
            </div>
            {simulating && <span className="simulating-indicator">Simulating...</span>}
          </div>

          {loading ? (
            <div className="chart-loading">
              <div className="spinner"></div>
              <p>Computing ARIMA / Prophet forecasts...</p>
            </div>
          ) : error ? (
            <div className="chart-error">
              <p>{error}</p>
              <button type="button" onClick={() => fetchBaseline(balance)} className="btn-secondary">
                Retry
              </button>
            </div>
          ) : (
            <div className="recharts-wrapper-box" style={{ width: '100%', height: 350 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 15, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.12)" />
                  <XAxis dataKey="date" stroke="#94a3b8" fontSize={11} tickLine={false} />
                  <YAxis
                    stroke="#94a3b8"
                    fontSize={11}
                    tickLine={false}
                    tickFormatter={(v) => `₹${v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgba(15, 23, 42, 0.95)',
                      borderColor: 'rgba(148, 163, 184, 0.25)',
                      borderRadius: '8px',
                      color: '#f8fafc',
                      fontSize: '12px',
                    }}
                    formatter={(val, name) => {
                      if (val === null || val === undefined) return ['—', name];
                      const labelMap = {
                        actual: 'Actual Spend',
                        forecast: 'Forecast Spend',
                        balance_remaining: 'Baseline Balance',
                        adjusted_balance: 'What-If Balance',
                      };
                      return [`₹${parseFloat(val).toFixed(2)}`, labelMap[name] || name];
                    }}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }}
                    formatter={(name) => {
                      const labels = {
                        actual: 'Historical Spend',
                        forecast: 'Forecast Spend',
                        balance_remaining: 'Baseline Balance',
                        adjusted_balance: 'What-If Balance',
                      };
                      return labels[name] || name;
                    }}
                  />

                  {/* Horizontal line at Balance = 0 */}
                  <ReferenceLine y={0} stroke="#ef4444" strokeDasharray="3 3" label="₹0 Depleted" />

                  {/* Historical spend */}
                  <Line
                    type="monotone"
                    dataKey="actual"
                    stroke="#818cf8"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    connectNulls
                  />
                  {/* Daily forecast spend */}
                  <Line
                    type="monotone"
                    dataKey="forecast"
                    stroke="#f59e0b"
                    strokeWidth={1.5}
                    strokeDasharray="4 4"
                    dot={false}
                    connectNulls
                  />
                  {/* Baseline balance remaining trajectory */}
                  <Line
                    type="monotone"
                    dataKey="balance_remaining"
                    stroke="#06b6d4"
                    strokeWidth={2.5}
                    dot={false}
                    connectNulls
                  />
                  {/* What-If adjusted balance trajectory */}
                  {whatIfData && (
                    <Line
                      type="monotone"
                      dataKey="adjusted_balance"
                      stroke="#10b981"
                      strokeWidth={3}
                      dot={false}
                      connectNulls
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Forecast Method Information Box */}
          <div className="forecast-explanation-box">
            <span className="info-icon">💡</span>
            <span>
              {baselineData?.distinct_days_history < 14 ? (
                <>
                  <strong>Cold-Start Active:</strong> You currently have{' '}
                  {baselineData.distinct_days_history} days of transactions. The model uses your
                  monthly allowance baseline until 14 days of data are recorded, after which ARIMA
                  time-series modeling automatically activates.
                </>
              ) : (
                <>
                  <strong>ARIMA Active:</strong> Trained on your last{' '}
                  {baselineData?.distinct_days_history} distinct spending days to capture weekly
                  cyclicality and spending variance.
                </>
              )}
            </span>
          </div>
        </div>

        {/* Right Side: What-If Simulator Panel */}
        <div className="whatif-panel glass-panel">
          <div className="whatif-header">
            <div>
              <h3 className="section-title">⚡ Try a What-If</h3>
              <p className="section-desc">Reduce category spending to stretch your runway date.</p>
            </div>
            {Object.values(adjustments).some((v) => v > 0) && (
              <button
                type="button"
                className="btn-reset-sliders"
                onClick={handleResetSliders}
                title="Reset all adjustments"
              >
                Reset Cuts
              </button>
            )}
          </div>

          {/* Outcome banner */}
          {daysSaved > 0 ? (
            <div className="whatif-outcome-banner banner-success">
              <span className="outcome-icon">🎉</span>
              <div>
                <strong className="outcome-title">+{daysSaved} Extra Days of Runway!</strong>
                <p className="outcome-text">
                  You’ll save ₹{moneySaved.toFixed(0)} over the next month, pushing your depletion
                  date to{' '}
                  <strong>
                    {new Date(activeRunwayDate).toLocaleDateString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                    })}
                  </strong>
                  .
                </p>
              </div>
            </div>
          ) : (
            <div className="whatif-outcome-banner banner-idle">
              <span className="outcome-icon">🎯</span>
              <div>
                <strong className="outcome-title">Simulate Expense Reductions</strong>
                <p className="outcome-text">
                  Slide below to test what happens if you cut Dining, Shopping, or Subs.
                </p>
              </div>
            </div>
          )}

          {/* Category Sliders List */}
          <div className="sliders-list">
            {CATEGORIES_LIST.map((cat) => {
              const val = adjustments[cat.name] || 0;
              const sharePercent =
                baselineData?.category_shares?.[cat.name] !== undefined
                  ? (baselineData.category_shares[cat.name] * 100).toFixed(0)
                  : '—';

              return (
                <div key={cat.name} className="slider-group">
                  <div className="slider-label-row">
                    <span className="cat-title">
                      <span className="cat-icon">{cat.icon}</span>
                      <span className="cat-name">{cat.name}</span>
                      {sharePercent !== '—' && (
                        <span className="share-pill">{sharePercent}% of spend</span>
                      )}
                    </span>
                    <span
                      className={`reduction-badge ${val > 0 ? 'badge-active' : ''}`}
                      style={{ color: val > 0 ? cat.color : '#94a3b8' }}
                    >
                      {val > 0 ? `-${val}%` : '0%'}
                    </span>
                  </div>

                  <input
                    type="range"
                    min="0"
                    max={cat.maxReduce}
                    step="5"
                    value={val}
                    onChange={(e) => handleSliderChange(cat.name, e.target.value)}
                    className="category-range-slider"
                    style={{
                      '--slider-color': cat.color,
                      '--slider-fill': `${(val / cat.maxReduce) * 100}%`,
                    }}
                    id={`slider-${cat.name.replace(/[^a-z0-9]/gi, '-')}`}
                  />
                  <div className="slider-limits">
                    <span>No cut</span>
                    <span>Max -{cat.maxReduce}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
