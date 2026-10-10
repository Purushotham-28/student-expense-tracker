import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { goalsService } from '../api';
import './Goals.css';

const GOAL_PRESETS = [
  { name: 'New Laptop', amount: 60000, days: 120, icon: '💻' },
  { name: 'Placement Suit & Prep', amount: 8000, days: 45, icon: '👔' },
  { name: 'Semester Exam Fees', amount: 4500, days: 30, icon: '📝' },
  { name: 'Hostel Deposit Fund', amount: 15000, days: 90, icon: '🏢' },
  { name: 'Emergency Rainy Day', amount: 10000, days: 60, icon: '🛡️' },
];

export default function Goals() {
  const navigate = useNavigate();
  const [goals, setGoals] = useState([]);
  const [summary, setSummary] = useState(null);
  const [evaluation, setEvaluation] = useState(null);
  const [activeTab, setActiveTab] = useState('active'); // 'active' | 'done' | 'all'
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Modals state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isSuggestionOpen, setIsSuggestionOpen] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState(null);
  const [suggestionLoading, setSuggestionLoading] = useState(false);

  // Contribution modal state
  const [contributeGoal, setContributeGoal] = useState(null);
  const [contributeAmount, setContributeAmount] = useState('');
  const [contributeSubmitting, setContributeSubmitting] = useState(false);
  const [celebrationMessage, setCelebrationMessage] = useState(null);

  // New goal form state
  const defaultDeadline = new Date(Date.now() + 60 * 24 * 60 * 60 * 1000)
    .toISOString()
    .split('T')[0];
  const [newGoal, setNewGoal] = useState({
    name: '',
    target_amount: '',
    saved_so_far: '0',
    deadline: defaultDeadline,
  });
  const [createSubmitting, setCreateSubmitting] = useState(false);

  const fetchGoals = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await goalsService.getGoals(activeTab);
      setGoals(res.goals || []);
      setSummary(res.summary || null);
      setEvaluation(res.evaluation || null);
    } catch (err) {
      console.error('Error fetching goals:', err);
      setError('Could not load savings goals. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGoals();
  }, [activeTab]);

  // Handle Preset selection
  const handleSelectPreset = (preset) => {
    const targetDate = new Date(Date.now() + preset.days * 24 * 60 * 60 * 1000)
      .toISOString()
      .split('T')[0];
    setNewGoal({
      name: preset.name,
      target_amount: preset.amount.toString(),
      saved_so_far: '0',
      deadline: targetDate,
    });
  };

  // Live weekly target preview for new goal form
  const getPreviewWeeklyTarget = () => {
    const target = parseFloat(newGoal.target_amount || 0);
    const saved = parseFloat(newGoal.saved_so_far || 0);
    const remaining = Math.max(0, target - saved);
    if (!newGoal.deadline || remaining <= 0) return 0;
    const diffDays = Math.max(
      1,
      Math.ceil((new Date(newGoal.deadline) - new Date()) / (1000 * 60 * 60 * 24))
    );
    const weeks = Math.max(1, diffDays / 7);
    return Math.round(remaining / weeks);
  };

  // Create Goal submit
  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    if (!newGoal.name.trim() || !newGoal.target_amount) return;

    try {
      setCreateSubmitting(true);
      await goalsService.createGoal({
        name: newGoal.name.trim(),
        target_amount: parseFloat(newGoal.target_amount),
        saved_so_far: parseFloat(newGoal.saved_so_far || 0),
        deadline: newGoal.deadline,
      });
      setIsCreateOpen(false);
      setNewGoal({
        name: '',
        target_amount: '',
        saved_so_far: '0',
        deadline: defaultDeadline,
      });
      await fetchGoals();
    } catch (err) {
      console.error('Failed to create goal:', err);
      alert('Error creating goal: ' + (err.response?.data?.target_amount || err.message));
    } finally {
      setCreateSubmitting(false);
    }
  };

  // Open "What should I cut?" suggestion
  const handleOpenSuggestion = async (goalId = null) => {
    setIsSuggestionOpen(true);
    setSuggestionLoading(true);
    try {
      const res = await goalsService.getSuggestion(goalId);
      setActiveSuggestion(res);
    } catch (err) {
      console.error('Error fetching cut suggestion:', err);
      setActiveSuggestion({
        is_behind: true,
        message: 'Could not fetch real-time diagnosis. Check your internet connection.',
      });
    } finally {
      setSuggestionLoading(false);
    }
  };

  // Contribute submit
  const handleContributeSubmit = async (e) => {
    e.preventDefault();
    if (!contributeGoal || !contributeAmount || parseFloat(contributeAmount) <= 0) return;

    try {
      setContributeSubmitting(true);
      const res = await goalsService.contribute(contributeGoal.id, parseFloat(contributeAmount));

      if (res.goal_completed) {
        setCelebrationMessage(
          `🎉 Congratulations! You achieved your goal '${contributeGoal.name}'!`
        );
        setTimeout(() => setCelebrationMessage(null), 7000);
      }

      setContributeGoal(null);
      setContributeAmount('');
      await fetchGoals();
    } catch (err) {
      console.error('Failed to contribute to goal:', err);
      alert('Error logging contribution: ' + (err.response?.data?.error || err.message));
    } finally {
      setContributeSubmitting(false);
    }
  };

  // Delete Goal
  const handleDeleteGoal = async (id, name) => {
    if (!window.confirm(`Are you sure you want to delete the goal '${name}'?`)) return;
    try {
      await goalsService.deleteGoal(id);
      await fetchGoals();
    } catch (err) {
      console.error('Error deleting goal:', err);
      alert('Failed to delete goal.');
    }
  };

  return (
    <div className="goals-container" id="goals-page">
      {/* Celebration Banner */}
      {celebrationMessage && (
        <div className="celebration-banner animate-fade-in" id="celebration-banner">
          <div className="celebration-icon">🏆</div>
          <div>
            <strong>Goal Completed!</strong>
            <p>{celebrationMessage}</p>
          </div>
          <button
            type="button"
            className="btn-close-toast"
            onClick={() => setCelebrationMessage(null)}
          >
            ✕
          </button>
        </div>
      )}

      {/* Header */}
      <div className="goals-header">
        <div>
          <div className="badge-chip">
            <span className="pulse-dot"></span>
            Adaptive Savings Engine
          </div>
          <h1 className="goals-title">Student Goal Planner</h1>
          <p className="goals-subtitle">
            Set ambitious college targets (laptop, exam fees, placement prep). Weekly saving targets
            adapt dynamically to your deposits and timeline.
          </p>
        </div>

        <div className="header-actions">
          <button
            type="button"
            className="btn-cut-action"
            onClick={() => handleOpenSuggestion(null)}
            id="btn-cut-suggestion-global"
          >
            <span className="btn-icon">💡</span>
            I'm Behind — What to Cut?
          </button>

          <button
            type="button"
            className="btn-create-goal"
            onClick={() => setIsCreateOpen(true)}
            id="btn-open-create-goal"
          >
            <span className="btn-icon">+</span>
            New Goal
          </button>
        </div>
      </div>

      {/* Background Health Check Alert Banner */}
      {evaluation && evaluation.has_active_goals && (
        <div
          className={`health-alert-banner ${evaluation.is_behind ? 'alert-behind' : 'alert-ontrack'}`}
          id="savings-health-banner"
        >
          <div className="alert-content">
            <span className="alert-emoji">{evaluation.is_behind ? '⚠️' : '🎯'}</span>
            <div>
              <strong>
                {evaluation.is_behind
                  ? 'Savings Velocity Alert: You Are Falling Behind'
                  : 'Savings Velocity: On Track'}
              </strong>
              <p>{evaluation.message}</p>
            </div>
          </div>

          {evaluation.is_behind && (
            <button
              type="button"
              className="btn-alert-cut"
              onClick={() => handleOpenSuggestion(null)}
              id="btn-banner-cut-solution"
            >
              View Cut Solution
            </button>
          )}
        </div>
      )}

      {/* Summary KPI Cards */}
      {summary && (
        <div className="kpi-grid">
          <div className="kpi-card">
            <div className="kpi-header">
              <span className="kpi-label">Total Target</span>
              <span className="kpi-icon">🎯</span>
            </div>
            <div className="kpi-value">₹{summary.total_target_amount?.toLocaleString()}</div>
            <div className="kpi-subtext">Across {summary.total_goals} recorded goals</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-header">
              <span className="kpi-label">Saved So Far</span>
              <span className="kpi-icon">💰</span>
            </div>
            <div className="kpi-value text-accent">
              ₹{summary.total_saved_so_far?.toLocaleString()}
            </div>
            <div className="kpi-progress-wrapper">
              <div
                className="kpi-progress-bar"
                style={{ width: `${Math.min(100, summary.overall_progress_pct || 0)}%` }}
              ></div>
            </div>
            <div className="kpi-subtext">{summary.overall_progress_pct}% overall completion</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-header">
              <span className="kpi-label">Needed Weekly Target</span>
              <span className="kpi-icon">⚡</span>
            </div>
            <div className="kpi-value text-highlight">
              ₹{summary.total_weekly_target?.toLocaleString()}
              <span className="kpi-unit">/wk</span>
            </div>
            <div className="kpi-subtext">Combined weekly burn across active goals</div>
          </div>

          <div className="kpi-card">
            <div className="kpi-header">
              <span className="kpi-label">Weekly Savings Rate</span>
              <span className="kpi-icon">📊</span>
            </div>
            <div className="kpi-value">
              ₹
              {evaluation
                ? Math.max(0, evaluation.actual_weekly_savings_rate || 0).toLocaleString()
                : '0'}
              <span className="kpi-unit">/wk</span>
            </div>
            <div className="kpi-subtext">
              {evaluation?.is_behind ? (
                <span className="status-pill status-behind">
                  -₹{evaluation.weekly_deficit?.toLocaleString()} deficit
                </span>
              ) : (
                <span className="status-pill status-ontrack">Healthy pace</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Navigation Filter Tabs */}
      <div className="tabs-bar">
        <div className="tabs-group">
          <button
            type="button"
            className={`tab-btn ${activeTab === 'active' ? 'active' : ''}`}
            onClick={() => setActiveTab('active')}
            id="tab-active-goals"
          >
            Active Goals ({goals.filter((g) => g.status === 'active').length})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'done' ? 'active' : ''}`}
            onClick={() => setActiveTab('done')}
            id="tab-done-goals"
          >
            Completed ({goals.filter((g) => g.status === 'done').length})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`}
            onClick={() => setActiveTab('all')}
            id="tab-all-goals"
          >
            All ({goals.length})
          </button>
        </div>
      </div>

      {/* Goals Content Area */}
      {loading ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Analyzing goals & calculating adaptive weekly rates...</p>
        </div>
      ) : error ? (
        <div className="error-card">
          <p>{error}</p>
          <button type="button" onClick={fetchGoals} className="btn-secondary">
            Retry
          </button>
        </div>
      ) : goals.length === 0 ? (
        <div className="empty-state-card" id="empty-goals-state">
          <div className="empty-icon">🎯</div>
          <h3>No goals found in this view</h3>
          <p>
            Create your first college savings goal to receive an intelligent, adaptive weekly target
            that shifts with your schedule!
          </p>
          <button
            type="button"
            className="btn-create-goal"
            onClick={() => setIsCreateOpen(true)}
          >
            + Create a Goal
          </button>
        </div>
      ) : (
        <div className="goals-grid" id="goals-list-grid">
          {goals.map((goal) => {
            const isDone = goal.status === 'done' || goal.saved_so_far >= goal.target_amount;
            const progress = goal.progress_percentage || 0;
            const remaining = Math.max(0, goal.target_amount - goal.saved_so_far);

            return (
              <div
                key={goal.id}
                className={`goal-card ${isDone ? 'goal-completed' : ''}`}
                id={`goal-card-${goal.id}`}
              >
                <div className="goal-card-top">
                  <div>
                    <h3 className="goal-name">{goal.name}</h3>
                    <div className="goal-deadline-text">
                      Target: {goal.deadline} • {goal.days_remaining} days left (~
                      {goal.weeks_remaining} wks)
                    </div>
                  </div>
                  <span className={`goal-status-badge ${isDone ? 'badge-done' : 'badge-active'}`}>
                    {isDone ? '✓ Completed' : 'Active'}
                  </span>
                </div>

                <div className="goal-amounts-row">
                  <div>
                    <span className="goal-amount-label">Saved</span>
                    <span className="goal-saved-val">₹{Number(goal.saved_so_far).toLocaleString()}</span>
                  </div>
                  <div className="text-right">
                    <span className="goal-amount-label">Target</span>
                    <span className="goal-target-val">₹{Number(goal.target_amount).toLocaleString()}</span>
                  </div>
                </div>

                {/* Progress bar */}
                <div className="goal-progress-track">
                  <div
                    className={`goal-progress-fill ${isDone ? 'fill-done' : ''}`}
                    style={{ width: `${Math.min(100, progress)}%` }}
                  ></div>
                </div>
                <div className="goal-progress-meta">
                  <span>{progress}% saved</span>
                  <span>₹{remaining.toLocaleString()} left</span>
                </div>

                {/* Weekly Target Highlight */}
                <div className="goal-weekly-highlight">
                  <div className="weekly-target-badge">
                    <span className="weekly-chip-label">Adaptive Weekly Target</span>
                    <span className="weekly-chip-value">
                      ₹{Number(goal.weekly_target).toLocaleString()}
                      <span className="weekly-period">/week</span>
                    </span>
                  </div>
                </div>

                {/* Card Actions */}
                <div className="goal-card-actions">
                  {!isDone ? (
                    <button
                      type="button"
                      className="btn-contribute"
                      onClick={() => {
                        setContributeGoal(goal);
                        setContributeAmount('');
                      }}
                      id={`btn-contribute-${goal.id}`}
                    >
                      + Deposit Funds
                    </button>
                  ) : (
                    <div className="badge-achieved">🎉 Achieved!</div>
                  )}

                  <button
                    type="button"
                    className="btn-card-cut"
                    title="What should I cut to reach this goal?"
                    onClick={() => handleOpenSuggestion(goal.id)}
                    id={`btn-cut-for-${goal.id}`}
                  >
                    ✂️ Trim
                  </button>

                  <button
                    type="button"
                    className="btn-card-delete"
                    title="Delete goal"
                    onClick={() => handleDeleteGoal(goal.id, goal.name)}
                    id={`btn-delete-${goal.id}`}
                  >
                    🗑️
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* CREATE GOAL MODAL */}
      {isCreateOpen && (
        <div className="modal-backdrop" onClick={() => setIsCreateOpen(false)}>
          <div
            className="modal-card modal-large animate-slide-up"
            onClick={(e) => e.stopPropagation()}
            id="create-goal-modal"
          >
            <div className="modal-header">
              <h2>Create College Savings Goal</h2>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setIsCreateOpen(false)}
              >
                ✕
              </button>
            </div>

            {/* Student Presets */}
            <div className="presets-section">
              <span className="presets-label">Quick Student Presets:</span>
              <div className="presets-list">
                {GOAL_PRESETS.map((p) => (
                  <button
                    key={p.name}
                    type="button"
                    className="preset-pill"
                    onClick={() => handleSelectPreset(p)}
                  >
                    {p.icon} {p.name} (₹{p.amount.toLocaleString()})
                  </button>
                ))}
              </div>
            </div>

            <form onSubmit={handleCreateSubmit} className="goal-form">
              <div className="form-group">
                <label>Goal Name</label>
                <input
                  type="text"
                  placeholder="e.g. M3 MacBook Air, Placement Suit, GRE Exam..."
                  value={newGoal.name}
                  onChange={(e) => setNewGoal({ ...newGoal, name: e.target.value })}
                  required
                  id="input-goal-name"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Target Amount (₹)</label>
                  <input
                    type="number"
                    min="100"
                    step="50"
                    placeholder="e.g. 50000"
                    value={newGoal.target_amount}
                    onChange={(e) => setNewGoal({ ...newGoal, target_amount: e.target.value })}
                    required
                    id="input-goal-target"
                  />
                </div>

                <div className="form-group">
                  <label>Already Saved (₹)</label>
                  <input
                    type="number"
                    min="0"
                    step="50"
                    placeholder="0"
                    value={newGoal.saved_so_far}
                    onChange={(e) => setNewGoal({ ...newGoal, saved_so_far: e.target.value })}
                    id="input-goal-saved"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Target Deadline</label>
                <input
                  type="date"
                  value={newGoal.deadline}
                  onChange={(e) => setNewGoal({ ...newGoal, deadline: e.target.value })}
                  required
                  id="input-goal-deadline"
                />
              </div>

              {/* Dynamic Preview */}
              {newGoal.target_amount && newGoal.deadline && (
                <div className="target-preview-box">
                  <span className="preview-label">Projected Adaptive Weekly Target:</span>
                  <span className="preview-rate">
                    ₹{getPreviewWeeklyTarget().toLocaleString()}/week
                  </span>
                  <span className="preview-note">
                    (Target adapts automatically whenever deposits or deadlines shift)
                  </span>
                </div>
              )}

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setIsCreateOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={createSubmitting}
                  id="btn-submit-goal"
                >
                  {createSubmitting ? 'Creating...' : 'Save & Calculate Target'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CONTRIBUTE / DEPOSIT MODAL */}
      {contributeGoal && (
        <div className="modal-backdrop" onClick={() => setContributeGoal(null)}>
          <div
            className="modal-card animate-slide-up"
            onClick={(e) => e.stopPropagation()}
            id="contribute-modal"
          >
            <div className="modal-header">
              <h2>Deposit to Goal</h2>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setContributeGoal(null)}
              >
                ✕
              </button>
            </div>

            <p className="contribute-target-name">
              Adding funds to <strong>{contributeGoal.name}</strong>
            </p>
            <div className="contribute-current-progress">
              Current: ₹{Number(contributeGoal.saved_so_far).toLocaleString()} / ₹
              {Number(contributeGoal.target_amount).toLocaleString()}
            </div>

            {/* Quick amount chips */}
            <div className="quick-chips">
              {[200, 500, 1000, 2000].map((amt) => (
                <button
                  key={amt}
                  type="button"
                  className="chip-btn"
                  onClick={() => setContributeAmount(amt.toString())}
                >
                  +₹{amt}
                </button>
              ))}
            </div>

            <form onSubmit={handleContributeSubmit} className="goal-form">
              <div className="form-group">
                <label>Deposit Amount (₹)</label>
                <input
                  type="number"
                  min="10"
                  step="10"
                  placeholder="Enter amount"
                  value={contributeAmount}
                  onChange={(e) => setContributeAmount(e.target.value)}
                  required
                  autoFocus
                  id="input-contribute-amount"
                />
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setContributeGoal(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={contributeSubmitting}
                  id="btn-confirm-contribute"
                >
                  {contributeSubmitting ? 'Recording...' : 'Confirm Deposit'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* "I'M BEHIND — WHAT SHOULD I CUT?" MODAL */}
      {isSuggestionOpen && (
        <div className="modal-backdrop" onClick={() => setIsSuggestionOpen(false)}>
          <div
            className="modal-card modal-large animate-slide-up suggestion-modal"
            onClick={(e) => e.stopPropagation()}
            id="cut-suggestion-modal"
          >
            <div className="modal-header">
              <div className="suggestion-title-group">
                <span className="suggestion-icon">💡</span>
                <h2>AI Spending Cut Recommendation</h2>
              </div>
              <button
                type="button"
                className="btn-close-modal"
                onClick={() => setIsSuggestionOpen(false)}
              >
                ✕
              </button>
            </div>

            {suggestionLoading ? (
              <div className="loading-state">
                <div className="spinner"></div>
                <p>Analyzing cash-flow run rate & forecasting discretionary trimmables...</p>
              </div>
            ) : activeSuggestion ? (
              <div className="suggestion-content">
                {/* Status Hero */}
                <div
                  className={`suggestion-hero ${activeSuggestion.is_behind ? 'hero-behind' : 'hero-ontrack'}`}
                >
                  <div className="hero-emoji">{activeSuggestion.is_behind ? '📉' : '🚀'}</div>
                  <div>
                    <h3 className="hero-title">
                      {activeSuggestion.is_behind
                        ? `Velocity Gap: ₹${activeSuggestion.weekly_deficit?.toLocaleString()}/week`
                        : 'On Pace to Achieve Your Targets!'}
                    </h3>
                    <p className="hero-msg">{activeSuggestion.message}</p>
                  </div>
                </div>

                {/* Key Metrics Comparison */}
                <div className="suggestion-comparison-row">
                  <div className="compare-card">
                    <span className="compare-label">Needed Target Rate</span>
                    <span className="compare-val text-highlight">
                      ₹{activeSuggestion.needed_weekly_rate?.toLocaleString()}
                      <span className="compare-unit">/wk</span>
                    </span>
                  </div>

                  <div className="compare-card">
                    <span className="compare-label">Your Current Net Savings</span>
                    <span className="compare-val">
                      ₹{Math.max(0, activeSuggestion.actual_weekly_savings_rate || 0).toLocaleString()}
                      <span className="compare-unit">/wk</span>
                    </span>
                  </div>

                  <div className="compare-card">
                    <span className="compare-label">Weekly Deficit</span>
                    <span
                      className={`compare-val ${activeSuggestion.is_behind ? 'text-danger' : 'text-accent'}`}
                    >
                      ₹{activeSuggestion.weekly_deficit?.toLocaleString()}
                      <span className="compare-unit">/wk</span>
                    </span>
                  </div>
                </div>

                {/* Recommended Trim Solution */}
                {activeSuggestion.is_behind && activeSuggestion.suggested_category && (
                  <div className="recommendation-box">
                    <div className="rec-header">
                      <span className="rec-tag">Recommended Strategy</span>
                      <h4>
                        Trim '{activeSuggestion.suggested_category}' by{' '}
                        {activeSuggestion.recommended_reduction_percent}%
                      </h4>
                    </div>
                    <p className="rec-description">
                      Based on your recent transactions and 30-day Prophet/ARIMA spending forecast,
                      reducing <strong>{activeSuggestion.suggested_category}</strong> spending can
                      recover:
                    </p>

                    <div className="rec-impact-grid">
                      <div className="impact-pill">
                        <span className="impact-num">
                          +₹{activeSuggestion.projected_weekly_savings?.toLocaleString()}
                        </span>
                        <span className="impact-desc">Weekly Cash Freed</span>
                      </div>
                      <div className="impact-pill">
                        <span className="impact-num">
                          +₹{activeSuggestion.projected_monthly_savings?.toLocaleString()}
                        </span>
                        <span className="impact-desc">30-Day Budget Savings</span>
                      </div>
                      <div className="impact-pill">
                        <span className="impact-num">
                          +{activeSuggestion.runway_days_gained || 7} days
                        </span>
                        <span className="impact-desc">Runway Extended</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Modal Footer Actions */}
                <div className="suggestion-actions">
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setIsSuggestionOpen(false)}
                  >
                    Close
                  </button>
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => {
                      setIsSuggestionOpen(false);
                      navigate('/runway');
                    }}
                    id="btn-goto-simulator"
                  >
                    Open What-If Runway Simulator →
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
