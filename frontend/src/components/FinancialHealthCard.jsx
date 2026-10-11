import React, { useState, useEffect } from 'react';
import { planningService } from '../api';
import './FinancialHealthCard.css';

export default function FinancialHealthCard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchScore = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await planningService.getHealthScore();
      setData(res);
    } catch (err) {
      console.error('Error fetching financial health score:', err);
      setError('Could not calculate financial health score.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScore();
  }, []);

  if (loading) {
    return (
      <div className="health-card glass-panel animate-fade-in" id="health-score-loading">
        <div className="health-loading-inner">
          <div className="spinner"></div>
          <p>Analyzing month-to-date savings, budget adherence & volatility...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="health-card glass-panel" id="health-score-error">
        <div className="health-error-inner">
          <p>{error || 'Score unavailable'}</p>
          <button type="button" onClick={fetchScore} className="btn-secondary">
            Retry
          </button>
        </div>
      </div>
    );
  }

  const { total_score, grade, status, summary, components, tips } = data;
  const savings = components.savings_rate;
  const budget = components.budget_adherence;
  const volatility = components.spending_volatility;

  // Determine theme color based on score
  let scoreColor = '#10b981'; // Green
  let scoreBg = 'rgba(16, 185, 129, 0.15)';
  if (total_score < 50) {
    scoreColor = '#ef4444'; // Red
    scoreBg = 'rgba(239, 68, 68, 0.15)';
  } else if (total_score < 70) {
    scoreColor = '#f59e0b'; // Amber
    scoreBg = 'rgba(245, 158, 11, 0.15)';
  } else if (total_score < 85) {
    scoreColor = '#6366f1'; // Indigo
    scoreBg = 'rgba(99, 102, 241, 0.15)';
  }

  // Gauge calculation (circumference for radius 54)
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (Math.min(100, total_score) / 100) * circumference;

  return (
    <div className="health-card glass-panel animate-fade-in" id="financial-health-card">
      <div className="health-card-header">
        <div className="header-title-wrap">
          <div className="header-badge-chip">
            <span className="pulse-dot" style={{ background: scoreColor }}></span>
            Month-To-Date Diagnostic
          </div>
          <h3 className="health-card-title">Financial Health Score</h3>
        </div>
        <button
          type="button"
          onClick={fetchScore}
          className="btn-refresh-health"
          title="Recalculate Score"
          id="btn-refresh-health-score"
        >
          ↻ Refresh
        </button>
      </div>

      <div className="health-card-body">
        {/* Gauge & Main Score Summary */}
        <div className="gauge-section">
          <div className="gauge-wrapper">
            <svg className="gauge-svg" viewBox="0 0 128 128">
              {/* Background track circle */}
              <circle
                cx="64"
                cy="64"
                r={radius}
                className="gauge-bg"
                strokeWidth="10"
              />
              {/* Animated Progress circle */}
              <circle
                cx="64"
                cy="64"
                r={radius}
                className="gauge-fill"
                strokeWidth="10"
                stroke={scoreColor}
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                transform="rotate(-90 64 64)"
              />
            </svg>

            <div className="gauge-center-text">
              <span className="gauge-score-num" style={{ color: scoreColor }}>
                {Math.round(total_score)}
              </span>
              <span className="gauge-scale">/ 100</span>
              <span
                className="gauge-grade-badge"
                style={{ background: scoreBg, color: scoreColor, borderColor: scoreColor }}
              >
                Grade {grade}
              </span>
            </div>
          </div>

          <div className="gauge-status-block">
            <div className="status-label-badge" style={{ color: scoreColor }}>
              {status}
            </div>
            <p className="status-summary-text">{summary}</p>
          </div>
        </div>

        {/* Breakdown Sub-scores */}
        <div className="breakdown-section">
          <h4 className="section-mini-heading">3-Pillar Breakdown</h4>

          {/* 1. Savings Rate */}
          <div className="pillar-item" id="pillar-savings">
            <div className="pillar-header">
              <div className="pillar-title-group">
                <span className="pillar-icon">💰</span>
                <span className="pillar-name">Savings Rate</span>
              </div>
              <span className="pillar-score-text">
                <strong>{savings.score}</strong> / 40 pts
              </span>
            </div>
            <div className="pillar-progress-track">
              <div
                className="pillar-progress-fill fill-savings"
                style={{ width: `${Math.min(100, savings.percentage)}%` }}
              ></div>
            </div>
            <div className="pillar-meta">
              <span>{savings.actual_rate}% net savings rate</span>
              <span>₹{savings.saved_amount?.toLocaleString()} saved</span>
            </div>
          </div>

          {/* 2. Budget Adherence */}
          <div className="pillar-item" id="pillar-budget">
            <div className="pillar-header">
              <div className="pillar-title-group">
                <span className="pillar-icon">🎯</span>
                <span className="pillar-name">Budget Adherence</span>
              </div>
              <span className="pillar-score-text">
                <strong>{budget.score}</strong> / 30 pts
              </span>
            </div>
            <div className="pillar-progress-track">
              <div
                className="pillar-progress-fill fill-budget"
                style={{ width: `${Math.min(100, budget.percentage)}%` }}
              ></div>
            </div>
            <div className="pillar-meta">
              <span>
                {budget.is_within_budget
                  ? 'Within budget limit'
                  : `Exceeded by ₹${budget.overspend_amount?.toLocaleString()}`}
              </span>
              <span>
                ₹{budget.spend?.toLocaleString()} / ₹{budget.budget_limit?.toLocaleString()}
              </span>
            </div>
          </div>

          {/* 3. Spending Volatility */}
          <div className="pillar-item" id="pillar-volatility">
            <div className="pillar-header">
              <div className="pillar-title-group">
                <span className="pillar-icon">🌊</span>
                <span className="pillar-name">Spending Stability</span>
              </div>
              <span className="pillar-score-text">
                <strong>{volatility.score}</strong> / 30 pts
              </span>
            </div>
            <div className="pillar-progress-track">
              <div
                className="pillar-progress-fill fill-volatility"
                style={{ width: `${Math.min(100, volatility.percentage)}%` }}
              ></div>
            </div>
            <div className="pillar-meta">
              <span>
                {volatility.coefficient_of_variation <= 0.15
                  ? 'High consistency across weeks'
                  : volatility.coefficient_of_variation <= 0.45
                  ? 'Moderate weekly fluctuation'
                  : 'Erratic weekly spend spikes'}
              </span>
              <span>CV: {volatility.coefficient_of_variation}</span>
            </div>
          </div>
        </div>

        {/* Actionable Tips Column */}
        <div className="tips-section">
          <h4 className="section-mini-heading">
            <span style={{ marginRight: '0.4rem' }}>💡</span>
            Tailored Financial Tips
          </h4>
          <div className="tips-list">
            {tips && tips.length > 0 ? (
              tips.map((tip, idx) => (
                <div key={idx} className="tip-card" id={`tip-item-${idx}`}>
                  <div className="tip-bullet">#{idx + 1}</div>
                  <p className="tip-text">{tip}</p>
                </div>
              ))
            ) : (
              <p className="no-tips">Keep up the great habits! Your financial health is solid.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
