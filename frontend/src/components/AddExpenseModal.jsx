import React, { useState } from 'react';
import { transactionService } from '../api';
import './AddExpenseModal.css';

export const EXPENSE_CATEGORIES = [
  { name: 'Food', icon: '🍔', color: '#f59e0b' },
  { name: 'Travel', icon: '🚗', color: '#3b82f6' },
  { name: 'Groceries/Shopping', icon: '🛒', color: '#10b981' },
  { name: 'Subscriptions', icon: '📺', color: '#8b5cf6' },
  { name: 'Rent/Hostel', icon: '🏠', color: '#ef4444' },
  { name: 'Academics', icon: '📚', color: '#06b6d4' },
  { name: 'Stationery', icon: '✏️', color: '#14b8a6' },
  { name: 'Utilities', icon: '💡', color: '#eab308' },
  { name: 'Friend/Split', icon: '👥', color: '#ec4899' },
  { name: 'Entertainment', icon: '🎬', color: '#f97316' },
  { name: 'Other', icon: '🏷️', color: '#64748b' },
];

export default function AddExpenseModal({ isOpen, onClose, onExpenseAdded }) {
  const todayStr = new Date().toISOString().split('T')[0];

  const [amount, setAmount] = useState('');
  const [category, setCategory] = useState('Food');
  const [payeeName, setPayeeName] = useState('');
  const [date, setDate] = useState(todayStr);
  const [paymentMode, setPaymentMode] = useState('UPI');
  const [saveMapping, setSaveMapping] = useState(true);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    const parsedAmount = parseFloat(amount);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      setError('Please enter a valid amount greater than ₹0.');
      return;
    }

    setLoading(true);
    setError('');
    setSuccessMsg('');

    try {
      const res = await transactionService.addManual({
        amount: parsedAmount.toFixed(2),
        category,
        payee_name: payeeName.trim(),
        date,
        payment_mode: paymentMode,
        save_mapping: saveMapping,
      });

      setSuccessMsg('Expense added successfully!');
      setTimeout(() => {
        if (onExpenseAdded) onExpenseAdded(res.transaction);
        // Reset form
        setAmount('');
        setPayeeName('');
        setDate(todayStr);
        setSuccessMsg('');
        onClose();
      }, 700);
    } catch (err) {
      const msg = err.response?.data?.error || err.message || 'Failed to add expense.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="add-expense-modal-overlay">
      <div className="add-expense-modal-card glass-panel">
        <div className="add-expense-modal-header">
          <div className="modal-title-row">
            <span className="modal-icon">➕</span>
            <h3 className="modal-title">Add Manual Expense</h3>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <p className="modal-desc">
          Quickly log a daily student expense (cash, UPI, or card) directly into your ledger and budget.
        </p>

        {error && (
          <div className="alert-box alert-error">
            <span>⚠️</span>
            <span>{error}</span>
          </div>
        )}
        {successMsg && (
          <div className="alert-box alert-success">
            <span>✅</span>
            <span>{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="add-expense-form">
          <div className="form-row">
            <div className="form-group flex-1">
              <label className="form-label" htmlFor="expense-amount">Amount (₹) *</label>
              <div className="input-with-prefix">
                <span className="input-prefix">₹</span>
                <input
                  id="expense-amount"
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="e.g. 80.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="form-input text-lg font-bold"
                  autoFocus
                  required
                />
              </div>
            </div>

            <div className="form-group flex-1">
              <label className="form-label" htmlFor="expense-category">Category *</label>
              <select
                id="expense-category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="form-input"
                required
              >
                {EXPENSE_CATEGORIES.map((cat) => (
                  <option key={cat.name} value={cat.name}>
                    {cat.icon} {cat.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="expense-payee">Payee / Description (Optional)</label>
            <input
              id="expense-payee"
              type="text"
              placeholder="e.g. Sri Rama Tiffin Centre, Campus Xerox, Nescafe"
              value={payeeName}
              onChange={(e) => setPayeeName(e.target.value)}
              className="form-input"
            />
          </div>

          <div className="form-row">
            <div className="form-group flex-1">
              <label className="form-label" htmlFor="expense-date">Date *</label>
              <input
                id="expense-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="form-input"
                required
              />
            </div>

            <div className="form-group flex-1">
              <label className="form-label">Payment Mode</label>
              <div className="mode-toggle-group">
                {['UPI', 'Cash', 'Card'].map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    className={`mode-btn ${paymentMode === mode ? 'active' : ''}`}
                    onClick={() => setPaymentMode(mode)}
                  >
                    {mode === 'UPI' ? '📱 UPI' : mode === 'Cash' ? '💵 Cash' : '💳 Card'}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {payeeName.trim() && (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={saveMapping}
                onChange={(e) => setSaveMapping(e.target.checked)}
              />
              <span>Remember "{payeeName.trim()}" as <strong>{category}</strong> for future statements</span>
            </label>
          )}

          <div className="modal-actions">
            <button type="button" className="btn-cancel" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className="btn-save" disabled={loading}>
              {loading ? 'Saving...' : '✓ Add Expense'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
