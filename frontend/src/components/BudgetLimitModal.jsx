import React, { useState } from 'react';
import { authService } from '../api';

export default function BudgetLimitModal({ isOpen, onClose, currentBudget, onBudgetUpdated, isOnboarding }) {
  const [budget, setBudget] = useState(currentBudget > 0 ? currentBudget : '500.00');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const presets = [300, 500, 750, 1000];

  const handleSave = async (e) => {
    e.preventDefault();
    const num = parseFloat(budget);
    if (isNaN(num) || num <= 0) {
      setError('Please enter a valid monthly budget limit greater than 0.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const updated = await authService.updateProfile({
        monthly_budget_limit: num.toFixed(2),
      });
      onBudgetUpdated(updated);
      onClose();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to update monthly budget limit.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content glass-panel" style={{ maxWidth: '480px' }}>
        <div className="modal-header">
          <div className="modal-badge-icon">🎯</div>
          <h3 className="modal-title">
            {isOnboarding ? 'Welcome! Set Your Monthly Budget' : 'Adjust Monthly Budget Limit'}
          </h3>
          <p className="modal-subtitle">
            {isOnboarding
              ? 'To get started, set your monthly spending cap so we can track burn rates and warn you before overspending.'
              : 'Update your spending target. Charts and budget gauges will automatically recalculate.'}
          </p>
        </div>

        {error && (
          <div className="auth-alert alert-error" style={{ marginBottom: '1rem' }}>
            <span>⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSave}>
          <div className="form-group">
            <label className="form-label" htmlFor="budget-input">
              Monthly Budget Limit ($)
            </label>
            <input
              id="budget-input"
              className="form-input"
              style={{ fontSize: '1.25rem', fontWeight: 700 }}
              type="number"
              step="10"
              min="1"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.5rem' }}>
              Quick Selection Presets:
            </span>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {presets.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  className="preset-chip"
                  onClick={() => setBudget(preset.toFixed(2))}
                  style={{
                    padding: '0.35rem 0.75rem',
                    borderRadius: 'var(--radius-full)',
                    background: parseFloat(budget) === preset ? 'var(--accent-primary)' : 'rgba(255,255,255,0.06)',
                    color: '#fff',
                    fontSize: '0.8rem',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  ${preset} / mo
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
            {!isOnboarding && (
              <button type="button" className="btn-secondary" onClick={onClose} disabled={loading}>
                Cancel
              </button>
            )}
            <button type="submit" className="btn-primary" disabled={loading} id="save-budget-btn">
              {loading ? 'Saving...' : isOnboarding ? 'Activate My Budget' : 'Update Limit'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
