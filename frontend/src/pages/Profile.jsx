import React, { useState, useEffect } from 'react';
import { authService, statementService, transactionService, goalsService } from '../api';
import './Profile.css';

export default function Profile({ userProfile, onProfileUpdated, onLogout }) {
  const [formData, setFormData] = useState({
    college_roll_number: userProfile?.college_roll_number || '',
    monthly_budget_limit: userProfile?.monthly_budget_limit || '15000',
    monthly_income: userProfile?.monthly_income || '25000',
  });
  const [stats, setStats] = useState({ statements: 0, transactions: 0, goals: 0 });
  const [loading, setLoading] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (userProfile) {
      setFormData({
        college_roll_number: userProfile.college_roll_number || '',
        monthly_budget_limit: userProfile.monthly_budget_limit || '15000',
        monthly_income: userProfile.monthly_income || '25000',
      });
    }

    // Load account activity stats
    Promise.allSettled([
      statementService.list(),
      transactionService.list({ pageSize: 1 }),
      goalsService.getGoals(),
    ]).then(([stmtsRes, txsRes, goalsRes]) => {
      setStats({
        statements: stmtsRes.status === 'fulfilled' ? (stmtsRes.value?.length || 0) : 0,
        transactions: txsRes.status === 'fulfilled' ? (txsRes.value?.counts?.all || 0) : 0,
        goals: goalsRes.status === 'fulfilled' ? (goalsRes.value?.goals?.length || 0) : 0,
      });
    });
  }, [userProfile]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg('');
    setSuccessMsg('');

    try {
      const budgetNum = parseFloat(formData.monthly_budget_limit);
      const incomeNum = parseFloat(formData.monthly_income);

      if (isNaN(budgetNum) || budgetNum <= 0) {
        throw new Error('Please enter a valid monthly budget limit greater than 0.');
      }

      const updated = await authService.updateProfile({
        college_roll_number: formData.college_roll_number.trim(),
        monthly_budget_limit: budgetNum.toFixed(2),
        monthly_income: !isNaN(incomeNum) ? incomeNum.toFixed(2) : '0.00',
      });

      setSuccessMsg('Profile and budget configurations updated successfully!');
      if (onProfileUpdated) {
        onProfileUpdated(updated);
      }
      setTimeout(() => setSuccessMsg(''), 4000);
    } catch (err) {
      setErrorMsg(err?.response?.data?.error || err.message || 'Failed to update profile.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="profile-page-container" id="student-profile-page">
      <div className="page-header">
        <div>
          <h2 className="page-title">Student Profile & Settings</h2>
          <p className="page-description">
            Manage your campus roll details, monthly allowance, and spending budget caps.
          </p>
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="btn-danger-outline"
          id="btn-profile-logout"
        >
          🚪 Sign Out
        </button>
      </div>

      {successMsg && (
        <div className="profile-alert profile-alert-success" id="profile-success-alert">
          <span>✅</span>
          <span>{successMsg}</span>
        </div>
      )}

      {errorMsg && (
        <div className="profile-alert profile-alert-error" id="profile-error-alert">
          <span>⚠️</span>
          <span>{errorMsg}</span>
        </div>
      )}

      <div className="profile-grid">
        {/* Profile Card */}
        <div className="profile-card-panel glass-panel">
          <div className="profile-avatar-wrap">
            <div className="profile-avatar-circle">
              {(userProfile?.username || 'S')[0].toUpperCase()}
            </div>
            <div className="profile-identity">
              <h3 className="profile-username">{userProfile?.username || 'Student User'}</h3>
              <p className="profile-email">{userProfile?.email || 'student@campus.edu'}</p>
              <span className="profile-badge">Active Student</span>
            </div>
          </div>

          <hr className="profile-divider" />

          <div className="profile-stats-row">
            <div className="profile-stat-box">
              <span className="profile-stat-num">{stats.statements}</span>
              <span className="profile-stat-lbl">Statements</span>
            </div>
            <div className="profile-stat-box">
              <span className="profile-stat-num">{stats.transactions}</span>
              <span className="profile-stat-lbl">Transactions</span>
            </div>
            <div className="profile-stat-box">
              <span className="profile-stat-num">{stats.goals}</span>
              <span className="profile-stat-lbl">Goals Set</span>
            </div>
          </div>
        </div>

        {/* Configuration Form */}
        <div className="profile-form-panel glass-panel">
          <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#f8fafc', marginBottom: '1.25rem' }}>
            Academic & Financial Configurations
          </h3>

          <form onSubmit={handleSubmit} className="profile-form">
            <div className="form-group">
              <label className="form-label" htmlFor="profile-roll">
                College Roll Number / Student ID
              </label>
              <input
                id="profile-roll"
                className="form-input"
                type="text"
                placeholder="e.g. CS2026-089"
                value={formData.college_roll_number}
                onChange={(e) => setFormData({ ...formData, college_roll_number: e.target.value })}
                required
              />
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Used to verify and tag student semester ledger records.
              </span>
            </div>

            <div className="form-row-2">
              <div className="form-group">
                <label className="form-label" htmlFor="profile-budget">
                  Monthly Budget Limit (₹)
                </label>
                <input
                  id="profile-budget"
                  className="form-input"
                  type="number"
                  step="100"
                  min="500"
                  placeholder="15000"
                  value={formData.monthly_budget_limit}
                  onChange={(e) => setFormData({ ...formData, monthly_budget_limit: e.target.value })}
                  required
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Triggers 80% & 100% alerts on category caps.
                </span>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="profile-income">
                  Monthly Income / Allowance (₹)
                </label>
                <input
                  id="profile-income"
                  className="form-input"
                  type="number"
                  step="100"
                  min="0"
                  placeholder="25000"
                  value={formData.monthly_income}
                  onChange={(e) => setFormData({ ...formData, monthly_income: e.target.value })}
                />
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Used for savings rate & health score calculations.
                </span>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem' }}>
              <button
                type="submit"
                className="btn-primary"
                disabled={loading}
                id="btn-save-profile"
                style={{ flex: 1, justifyContent: 'center' }}
              >
                {loading ? 'Saving Changes...' : '💾 Update Profile Settings'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
