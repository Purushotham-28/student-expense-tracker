import React, { useState } from 'react';
import { transactionService } from '../api';
import { EXPENSE_CATEGORIES } from './AddExpenseModal';
import './QuickExpenseBar.css';

export default function QuickExpenseBar({ onExpenseAdded, onOpenFullModal }) {
  const [amount, setAmount] = useState('');
  const [category, setCategory] = useState('Food');
  const [payee, setPayee] = useState('');
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');

  const handleQuickSubmit = async (e) => {
    e.preventDefault();
    const parsedAmount = parseFloat(amount);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      setStatusMsg('Enter valid amount');
      setTimeout(() => setStatusMsg(''), 2500);
      return;
    }

    setLoading(true);
    setStatusMsg('');

    try {
      const res = await transactionService.addManual({
        amount: parsedAmount.toFixed(2),
        category,
        payee_name: payee.trim(),
        payment_mode: 'UPI',
        save_mapping: true,
      });

      setStatusMsg('Logged! ✓');
      setAmount('');
      setPayee('');
      setTimeout(() => setStatusMsg(''), 2000);
      if (onExpenseAdded) onExpenseAdded(res.transaction);
    } catch (err) {
      setStatusMsg('Failed ✕');
      setTimeout(() => setStatusMsg(''), 2500);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="quick-expense-container glass-panel">
      <div className="quick-expense-label">
        <span className="zap-icon">⚡</span>
        <span className="quick-title">Quick Log</span>
      </div>

      <form onSubmit={handleQuickSubmit} className="quick-expense-form">
        <div className="quick-input-group quick-amount-wrap">
          <span className="quick-currency">₹</span>
          <input
            type="number"
            step="0.01"
            min="0.01"
            placeholder="Amount"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="quick-input quick-amount-input"
            required
          />
        </div>

        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="quick-select"
        >
          {EXPENSE_CATEGORIES.map((c) => (
            <option key={c.name} value={c.name}>
              {c.icon} {c.name}
            </option>
          ))}
        </select>

        <input
          type="text"
          placeholder="Payee (e.g. Chai, Auto)"
          value={payee}
          onChange={(e) => setPayee(e.target.value)}
          className="quick-input quick-payee-input"
        />

        <button type="submit" className="quick-submit-btn" disabled={loading}>
          {loading ? '...' : statusMsg ? statusMsg : '+ Log Expense'}
        </button>

        {onOpenFullModal && (
          <button
            type="button"
            className="quick-more-btn"
            onClick={onOpenFullModal}
            title="Open full expense form"
          >
            More Details ↗
          </button>
        )}
      </form>
    </div>
  );
}
