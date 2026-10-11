import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { transactionService } from '../api';
import './Verify.css';

const CATEGORIES = [
  { name: 'Food', icon: '🍔', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' },
  { name: 'Travel', icon: '🚗', color: '#3b82f6', bg: 'rgba(59, 130, 246, 0.12)' },
  { name: 'Groceries/Shopping', icon: '🛒', color: '#10b981', bg: 'rgba(16, 185, 129, 0.12)' },
  { name: 'Subscriptions', icon: '📺', color: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.12)' },
  { name: 'Rent/Hostel', icon: '🏠', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)' },
  { name: 'Academics', icon: '📚', color: '#06b6d4', bg: 'rgba(6, 182, 212, 0.12)' },
  { name: 'Friend/Split', icon: '👥', color: '#ec4899', bg: 'rgba(236, 72, 153, 0.12)' },
  { name: 'Entertainment', icon: '🎬', color: '#f97316', bg: 'rgba(249, 115, 22, 0.12)' },
  { name: 'Other', icon: '🏷️', color: '#64748b', bg: 'rgba(100, 116, 139, 0.12)' },
];

export default function Verify() {
  const navigate = useNavigate();

  // Active tab: 'review' (pending + verify), 'pending', 'verify', 'auto'
  const [activeTab, setActiveTab] = useState('review');
  const [transactions, setTransactions] = useState([]);
  const [counts, setCounts] = useState({ all: 0, auto: 0, verify: 0, pending: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // Per-payee group state: applyToAll checkbox (default true per payee)
  const [applyToAllMap, setApplyToAllMap] = useState({});
  // Action in progress (by txId or payeeKey)
  const [confirmingMap, setConfirmingMap] = useState({});
  // Toast notifications
  const [toast, setToast] = useState(null);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  }, []);

  // Fetch transactions based on tab
  const fetchTransactions = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      let statusParam = activeTab;
      if (activeTab === 'review') {
        // Fetch all transactions and filter locally for pending + verify
        statusParam = 'all';
      }

      const data = await transactionService.list({
        status: statusParam,
        pageSize: 100,
      });

      let items = data.results || [];
      if (activeTab === 'review') {
        items = items.filter(
          (t) => t.status === 'verify' || t.status === 'pending'
        );
        // Sort with pending first, then by amount descending
        items.sort((a, b) => {
          if (a.status === 'pending' && b.status !== 'pending') return -1;
          if (b.status === 'pending' && a.status !== 'pending') return 1;
          return parseFloat(b.amount) - parseFloat(a.amount);
        });
      }

      setTransactions(items);
      if (data.counts) {
        setCounts(data.counts);
      }
    } catch (err) {
      setError(err?.response?.data?.error || 'Failed to load transactions.');
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  // Group transactions by Payee
  const groupedPayees = useMemo(() => {
    let filtered = transactions;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      filtered = transactions.filter(
        (t) =>
          (t.payee_name && t.payee_name.toLowerCase().includes(q)) ||
          (t.upi_id && t.upi_id.toLowerCase().includes(q)) ||
          (t.remark && t.remark.toLowerCase().includes(q))
      );
    }

    const groups = {};
    filtered.forEach((tx) => {
      const key = (tx.upi_id || tx.payee_name || 'Unknown Payee')
        .toLowerCase()
        .trim();
      if (!groups[key]) {
        groups[key] = {
          key,
          displayName: tx.payee_name || tx.upi_id || 'Unknown Payee',
          upiId: tx.upi_id || '',
          transactions: [],
          totalAmount: 0,
          pendingCount: 0,
          verifyCount: 0,
          suggestedCategory: tx.category || 'Other',
          suggestedConfidence: tx.confidence || 0,
        };
      }
      groups[key].transactions.push(tx);
      groups[key].totalAmount += parseFloat(tx.amount || 0);
      if (tx.status === 'pending') groups[key].pendingCount += 1;
      if (tx.status === 'verify') groups[key].verifyCount += 1;
      // Track highest confidence suggestion
      if ((tx.confidence || 0) > groups[key].suggestedConfidence) {
        groups[key].suggestedConfidence = tx.confidence;
        groups[key].suggestedCategory = tx.category;
      }
    });

    return Object.values(groups);
  }, [transactions, searchQuery]);

  // Handle one-tap confirmation for a category
  const handleConfirmCategory = async (group, tx, chosenCategory) => {
    const applyToAll = applyToAllMap[group.key] !== false; // Default true!
    const targetTx = tx || group.transactions[0];
    if (!targetTx) return;

    setConfirmingMap((prev) => ({ ...prev, [group.key]: true }));

    try {
      const res = await transactionService.confirm(targetTx.id, {
        category: chosenCategory,
        applyToAll: applyToAll,
      });

      showToast(
        `✓ Assigned "${chosenCategory}" to ${group.displayName} (${res.updated_count || 1} updated)`,
        'success'
      );

      // Optimistically remove confirmed items from review list if in review tab
      if (activeTab === 'review' || activeTab === 'pending' || activeTab === 'verify') {
        const confirmedIds = new Set(
          applyToAll
            ? group.transactions.map((t) => t.id)
            : [targetTx.id]
        );
        setTransactions((prev) => prev.filter((t) => !confirmedIds.has(t.id)));

        // Update counts
        setCounts((prev) => ({
          ...prev,
          auto: prev.auto + confirmedIds.size,
          pending: Math.max(0, prev.pending - (group.pendingCount || 0)),
          verify: Math.max(0, prev.verify - (group.verifyCount || 0)),
        }));
      } else {
        // In 'auto' or 'all', re-fetch to reflect updated status
        fetchTransactions();
      }
    } catch (err) {
      showToast(
        err?.response?.data?.error || 'Failed to confirm category.',
        'error'
      );
    } finally {
      setConfirmingMap((prev) => ({ ...prev, [group.key]: false }));
    }
  };

  const toggleApplyToAll = (groupKey) => {
    setApplyToAllMap((prev) => ({
      ...prev,
      [groupKey]: prev[groupKey] === false ? true : false,
    }));
  };

  const reviewNeededCount = (counts.pending || 0) + (counts.verify || 0);

  return (
    <div className="verify-page">
      {/* Toast Notification */}
      {toast && (
        <div className={`verify-toast ${toast.type}`}>
          <span>{toast.message}</span>
        </div>
      )}

      {/* Page Header */}
      <div className="verify-header">
        <div>
          <div className="header-badge-row">
            <h1 className="verify-title">Needs Your Review</h1>
            {reviewNeededCount > 0 && (
              <span className="review-badge-count">{reviewNeededCount} pending</span>
            )}
          </div>
          <p className="verify-subtitle">
            Antigravity automatically categorized high-confidence items. Verify uncertain
            transactions to personalize your ML categorizer.
          </p>
        </div>

        <button
          type="button"
          className="btn-upload-more"
          onClick={() => navigate('/upload')}
        >
          + Upload Statement
        </button>
      </div>

      {/* Routing Summary Cards */}
      <div className="verify-stats-grid">
        <div
          className={`stat-pill-card ${activeTab === 'review' ? 'active-card' : ''}`}
          onClick={() => setActiveTab('review')}
        >
          <div className="pill-card-icon" style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#ef4444' }}>
            ⚡
          </div>
          <div>
            <div className="pill-card-num">{reviewNeededCount}</div>
            <div className="pill-card-label">To Review (Pending + Verify)</div>
          </div>
        </div>

        <div
          className={`stat-pill-card ${activeTab === 'pending' ? 'active-card' : ''}`}
          onClick={() => setActiveTab('pending')}
        >
          <div className="pill-card-icon" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>
            ❓
          </div>
          <div>
            <div className="pill-card-num">{counts.pending || 0}</div>
            <div className="pill-card-label">Needs Help (&lt;50% conf)</div>
          </div>
        </div>

        <div
          className={`stat-pill-card ${activeTab === 'verify' ? 'active-card' : ''}`}
          onClick={() => setActiveTab('verify')}
        >
          <div className="pill-card-icon" style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#3b82f6' }}>
            🔍
          </div>
          <div>
            <div className="pill-card-num">{counts.verify || 0}</div>
            <div className="pill-card-label">To Verify (50–80% conf)</div>
          </div>
        </div>

        <div
          className={`stat-pill-card ${activeTab === 'auto' ? 'active-card' : ''}`}
          onClick={() => setActiveTab('auto')}
        >
          <div className="pill-card-icon" style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#10b981' }}>
            ✨
          </div>
          <div>
            <div className="pill-card-num">{counts.auto || 0}</div>
            <div className="pill-card-label">Auto-Categorized (&ge;80%)</div>
          </div>
        </div>
      </div>

      {/* Tabs & Filter Bar */}
      <div className="verify-toolbar glass-panel">
        <div className="verify-tabs">
          <button
            type="button"
            className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`}
            onClick={() => setActiveTab('all')}
            id="tab-all-txs"
          >
            All ({counts.all || 0})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'review' ? 'active' : ''}`}
            onClick={() => setActiveTab('review')}
            id="tab-review-all"
          >
            Review Queue ({reviewNeededCount})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'pending' ? 'active' : ''}`}
            onClick={() => setActiveTab('pending')}
            id="tab-pending"
          >
            Needs Help ({counts.pending || 0})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'verify' ? 'active' : ''}`}
            onClick={() => setActiveTab('verify')}
            id="tab-verify"
          >
            Verify Suggestions ({counts.verify || 0})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'auto' ? 'active' : ''}`}
            onClick={() => setActiveTab('auto')}
            id="tab-auto"
          >
            Auto Resolved ({counts.auto || 0})
          </button>
        </div>

        <div className="search-box">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Filter by payee name or UPI..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
            id="verify-search-input"
          />
          {searchQuery && (
            <button
              type="button"
              className="clear-search-btn"
              onClick={() => setSearchQuery('')}
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* Content Area */}
      {loading ? (
        <div className="loading-state glass-panel">
          <div className="spinner"></div>
          <p>Loading transactions...</p>
        </div>
      ) : error ? (
        <div className="error-banner glass-panel">
          <p>{error}</p>
          <button type="button" onClick={fetchTransactions} className="btn-secondary">
            Retry
          </button>
        </div>
      ) : groupedPayees.length === 0 ? (
        <div className="empty-state glass-panel">
          <div className="empty-icon">🎉</div>
          <h3 className="empty-title">All Caught Up!</h3>
          <p className="empty-description">
            {activeTab === 'auto'
              ? 'No auto-categorized transactions found yet.'
              : 'There are no pending or uncertain transactions to review. Great job!'}
          </p>
          <div className="empty-actions">
            <button
              type="button"
              className="btn-primary"
              onClick={() => navigate('/upload')}
            >
              Upload New Statement
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => navigate('/')}
            >
              Back to Dashboard
            </button>
          </div>
        </div>
      ) : (
        <div className="payee-groups-list">
          {groupedPayees.map((group) => {
            const isApplyToAll = applyToAllMap[group.key] !== false; // default true
            const isConfirming = confirmingMap[group.key];

            return (
              <div
                key={group.key}
                className="payee-card glass-panel"
                id={`payee-card-${group.key.replace(/[^a-z0-9]/g, '-')}`}
              >
                {/* Payee Header */}
                <div className="payee-card-header">
                  <div className="payee-meta">
                    <div className="payee-avatar">
                      {group.displayName.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <div className="payee-title-row">
                        <h3 className="payee-name">{group.displayName}</h3>
                        {group.upiId && (
                          <span className="payee-upi-badge">{group.upiId}</span>
                        )}
                      </div>
                      <div className="payee-sub-row">
                        <span className="tx-count-pill">
                          {group.transactions.length}{' '}
                          {group.transactions.length === 1 ? 'transaction' : 'transactions'}
                        </span>
                        <span className="tx-total-amount">
                          Total: ₹{group.totalAmount.toFixed(2)}
                        </span>
                        {group.pendingCount > 0 && (
                          <span className="status-tag status-tag-pending">
                            {group.pendingCount} needs help
                          </span>
                        )}
                        {group.verifyCount > 0 && (
                          <span className="status-tag status-tag-verify">
                            {group.verifyCount} to verify
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Apply to all checkbox (default checked on) */}
                  <label className="apply-to-all-toggle">
                    <input
                      type="checkbox"
                      checked={isApplyToAll}
                      onChange={() => toggleApplyToAll(group.key)}
                      id={`apply-all-checkbox-${group.key}`}
                    />
                    <span className="toggle-text">
                      Apply to all {group.transactions.length} from this payee
                    </span>
                  </label>
                </div>

                {/* AI Suggestion Banner if available */}
                {group.suggestedCategory && group.suggestedConfidence > 0 && (
                  <div className="ai-suggestion-strip">
                    <span className="ai-icon">🤖 AI Suggestion:</span>
                    <strong className="ai-suggested-name">{group.suggestedCategory}</strong>
                    <span className="ai-confidence-pill">
                      {(group.suggestedConfidence * 100).toFixed(0)}% confidence
                    </span>
                    <span className="ai-hint">
                      — Click below to confirm or select the correct category:
                    </span>
                  </div>
                )}

                {/* One-Tap Category Buttons */}
                <div className="category-button-grid">
                  {CATEGORIES.map((cat) => {
                    const isSuggested =
                      group.suggestedCategory?.toLowerCase() === cat.name.toLowerCase();

                    return (
                      <button
                        key={cat.name}
                        type="button"
                        className={`cat-btn ${isSuggested ? 'cat-btn-suggested' : ''}`}
                        style={{
                          '--cat-color': cat.color,
                          '--cat-bg': cat.bg,
                        }}
                        disabled={isConfirming}
                        onClick={() => handleConfirmCategory(group, null, cat.name)}
                        title={`Categorize as ${cat.name}`}
                        id={`btn-${group.key}-${cat.name.replace(/[^a-z0-9]/gi, '-')}`}
                      >
                        <span className="cat-icon">{cat.icon}</span>
                        <span className="cat-text">{cat.name}</span>
                        {isSuggested && <span className="cat-star">★</span>}
                      </button>
                    );
                  })}
                </div>

                {/* Transaction Rows inside this group */}
                <div className="tx-table-wrapper">
                  <table className="tx-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Remark / Raw Description</th>
                        <th>Confidence</th>
                        <th>Status</th>
                        <th style={{ textAlign: 'right' }}>Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.transactions.map((tx) => (
                        <tr key={tx.id} className="tx-row">
                          <td className="tx-date">
                            {tx.date
                              ? new Date(tx.date).toLocaleDateString('en-IN', {
                                  day: 'numeric',
                                  month: 'short',
                                  year: 'numeric',
                                })
                              : '—'}
                          </td>
                          <td className="tx-remark">
                            <span className="remark-text">
                              {tx.remark || tx.raw_text || '—'}
                            </span>
                          </td>
                          <td className="tx-conf">
                            {tx.confidence !== null && tx.confidence !== undefined ? (
                              <span
                                className={`conf-badge ${
                                  tx.confidence >= 0.8
                                    ? 'conf-high'
                                    : tx.confidence >= 0.5
                                    ? 'conf-medium'
                                    : 'conf-low'
                                }`}
                              >
                                {(tx.confidence * 100).toFixed(0)}%
                              </span>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="tx-status-col">
                            <span className={`status-pill status-${tx.status}`}>
                              {tx.status}
                            </span>
                          </td>
                          <td className="tx-amount-cell">
                            ₹{parseFloat(tx.amount || 0).toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
