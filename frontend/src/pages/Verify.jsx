import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { transactionService } from '../api';
import AddExpenseModal from '../components/AddExpenseModal';
import QuickExpenseBar from '../components/QuickExpenseBar';
import DeleteConfirmationModal from '../components/DeleteConfirmationModal';
import './Verify.css';

const CATEGORIES = [
  { name: 'Food', icon: '🍔', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' },
  { name: 'Travel', icon: '🚗', color: '#3b82f6', bg: 'rgba(59, 130, 246, 0.12)' },
  { name: 'Groceries/Shopping', icon: '🛒', color: '#10b981', bg: 'rgba(16, 185, 129, 0.12)' },
  { name: 'Subscriptions', icon: '📺', color: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.12)' },
  { name: 'Rent/Hostel', icon: '🏠', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)' },
  { name: 'Academics', icon: '📚', color: '#06b6d4', bg: 'rgba(6, 182, 212, 0.12)' },
  { name: 'Stationery', icon: '✏️', color: '#14b8a6', bg: 'rgba(20, 184, 166, 0.12)' },
  { name: 'Utilities', icon: '💡', color: '#eab308', bg: 'rgba(234, 179, 8, 0.12)' },
  { name: 'Friend/Split', icon: '👥', color: '#ec4899', bg: 'rgba(236, 72, 153, 0.12)' },
  { name: 'Entertainment', icon: '🎬', color: '#f97316', bg: 'rgba(249, 115, 22, 0.12)' },
  { name: 'Other', icon: '🏷️', color: '#64748b', bg: 'rgba(100, 116, 139, 0.12)' },
];

export default function Verify() {
  const navigate = useNavigate();

  // Active tab: 'review', 'all', 'auto', 'duplicate', 'deleted'
  const [activeTab, setActiveTab] = useState('review');
  const [transactions, setTransactions] = useState([]);
  const [counts, setCounts] = useState({ all: 0, auto: 0, verify: 0, pending: 0, duplicate: 0, deleted: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [isAddExpenseModalOpen, setIsAddExpenseModalOpen] = useState(false);

  // Multi-select for bulk delete / bulk restore
  const [selectedIds, setSelectedIds] = useState(new Set());

  // Delete confirmation modal state
  const [deleteModal, setDeleteModal] = useState({
    isOpen: false,
    item: null,
    isBulk: false,
    loading: false,
  });

  // Per-payee group state: applyToAll checkbox (default true per payee)
  const [applyToAllMap, setApplyToAllMap] = useState({});
  // Action in progress (by txId or payeeKey)
  const [confirmingMap, setConfirmingMap] = useState({});
  // Toast notifications
  const [toast, setToast] = useState(null);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  }, []);

  // Fetch transactions based on tab
  const fetchTransactions = useCallback(async () => {
    setLoading(true);
    setError('');
    setSelectedIds(new Set());
    try {
      let statusParam = activeTab;
      if (activeTab === 'review') {
        statusParam = 'all';
      }

      const data = await transactionService.list({
        status: statusParam,
        pageSize: 150,
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

  // Filter transactions by search query
  const filteredTransactions = useMemo(() => {
    if (!searchQuery.trim()) return transactions;
    const q = searchQuery.toLowerCase().trim();
    return transactions.filter(
      (t) =>
        (t.payee_name && t.payee_name.toLowerCase().includes(q)) ||
        (t.upi_id && t.upi_id.toLowerCase().includes(q)) ||
        (t.remark && t.remark.toLowerCase().includes(q)) ||
        (t.category && t.category.toLowerCase().includes(q))
    );
  }, [transactions, searchQuery]);

  // Group transactions by Payee for review tab
  const groupedPayees = useMemo(() => {
    const groups = {};
    filteredTransactions.forEach((tx) => {
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
      if ((tx.confidence || 0) > groups[key].suggestedConfidence) {
        groups[key].suggestedConfidence = tx.confidence;
        groups[key].suggestedCategory = tx.category;
      }
    });

    return Object.values(groups);
  }, [filteredTransactions]);

  // Checkbox selection handlers
  const handleToggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedIds.size === filteredTransactions.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredTransactions.map((t) => t.id)));
    }
  };

  // Open single delete confirmation
  const handleRequestDelete = (tx) => {
    setDeleteModal({
      isOpen: true,
      item: tx,
      isBulk: false,
      loading: false,
    });
  };

  // Open bulk delete confirmation
  const handleRequestBulkDelete = () => {
    if (selectedIds.size === 0) return;
    setDeleteModal({
      isOpen: true,
      item: null,
      isBulk: true,
      loading: false,
    });
  };

  // Execute deletion (soft-delete)
  const handleConfirmDelete = async () => {
    setDeleteModal((prev) => ({ ...prev, loading: true }));
    try {
      if (deleteModal.isBulk) {
        const ids = Array.from(selectedIds);
        const res = await transactionService.bulkDelete(ids);
        showToast(
          `🗑️ ${res.deleted_count || ids.length} transaction(s) moved to recently deleted. Payee rules preserved.`,
          'success'
        );
      } else if (deleteModal.item) {
        await transactionService.delete(deleteModal.item.id);
        showToast(
          `🗑️ Transaction moved to recently deleted. Payee rules preserved.`,
          'success'
        );
      }
      setDeleteModal({ isOpen: false, item: null, isBulk: false, loading: false });
      fetchTransactions();
    } catch (err) {
      showToast(err?.response?.data?.error || 'Failed to delete transaction.', 'error');
      setDeleteModal((prev) => ({ ...prev, loading: false }));
    }
  };

  // Restore single transaction
  const handleRestore = async (txId) => {
    try {
      await transactionService.restore(txId);
      showToast('🔄 Transaction restored successfully.', 'success');
      fetchTransactions();
    } catch (err) {
      showToast(err?.response?.data?.error || 'Failed to restore transaction.', 'error');
    }
  };

  // Bulk restore transactions
  const handleBulkRestore = async () => {
    if (selectedIds.size === 0) return;
    try {
      const ids = Array.from(selectedIds);
      const res = await transactionService.bulkRestore(ids);
      showToast(`🔄 ${res.restored_count || ids.length} transaction(s) restored.`, 'success');
      fetchTransactions();
    } catch (err) {
      showToast(err?.response?.data?.error || 'Failed to restore transactions.', 'error');
    }
  };

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

      if (activeTab === 'review') {
        const confirmedIds = new Set(
          applyToAll
            ? group.transactions.map((t) => t.id)
            : [targetTx.id]
        );
        setTransactions((prev) => prev.filter((t) => !confirmedIds.has(t.id)));
        setCounts((prev) => ({
          ...prev,
          auto: (prev.auto || 0) + confirmedIds.size,
          pending: Math.max(0, (prev.pending || 0) - (group.pendingCount || 0)),
          verify: Math.max(0, (prev.verify || 0) - (group.verifyCount || 0)),
        }));
      } else {
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
            <h1 className="verify-title">
              {activeTab === 'deleted' ? 'Recently Deleted' : 'Transactions & Review'}
            </h1>
            {activeTab === 'deleted' ? (
              <span className="review-badge-count" style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#f87171' }}>
                {counts.deleted || 0} in trash
              </span>
            ) : reviewNeededCount > 0 ? (
              <span className="review-badge-count">{reviewNeededCount} pending</span>
            ) : null}
          </div>
          <p className="verify-subtitle">
            {activeTab === 'deleted'
              ? 'Accidentally deleted an expense? Restore it here with one tap. Deleted transactions are excluded from your budget, runway, and health score.'
              : 'Categorize, manage, or delete expenses. Any payee rules you establish are preserved even if you remove transactions.'}
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <button
            type="button"
            className="btn-add-expense"
            id="btn-verify-add-expense"
            onClick={() => setIsAddExpenseModalOpen(true)}
            style={{
              background: 'linear-gradient(135deg, #10b981, #059669)',
              color: '#fff',
              border: 'none',
              padding: '0.65rem 1.15rem',
              borderRadius: '10px',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(16, 185, 129, 0.35)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
            }}
          >
            ➕ Add Expense
          </button>
          <button
            type="button"
            className="btn-upload-more"
            onClick={() => navigate('/upload')}
          >
            + Upload Statement
          </button>
        </div>
      </div>

      {/* ── Quick Expense Logging (Hidden in Trash) ── */}
      {activeTab !== 'deleted' && (
        <QuickExpenseBar
          onExpenseAdded={fetchTransactions}
          onOpenFullModal={() => setIsAddExpenseModalOpen(true)}
        />
      )}

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
            <div className="pill-card-label">To Review</div>
          </div>
        </div>

        <div
          className={`stat-pill-card ${activeTab === 'all' ? 'active-card' : ''}`}
          onClick={() => setActiveTab('all')}
        >
          <div className="pill-card-icon" style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#3b82f6' }}>
            📊
          </div>
          <div>
            <div className="pill-card-num">{counts.all || 0}</div>
            <div className="pill-card-label">All Active Expenses</div>
          </div>
        </div>

        <div
          className={`stat-pill-card ${activeTab === 'duplicate' ? 'active-card' : ''}`}
          onClick={() => setActiveTab('duplicate')}
        >
          <div className="pill-card-icon" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>
            ⚠️
          </div>
          <div>
            <div className="pill-card-num">{counts.duplicate || 0}</div>
            <div className="pill-card-label">Duplicates Flagged</div>
          </div>
        </div>

        <div
          className={`stat-pill-card ${activeTab === 'deleted' ? 'active-card' : ''}`}
          onClick={() => setActiveTab('deleted')}
        >
          <div className="pill-card-icon" style={{ background: 'rgba(148, 163, 184, 0.15)', color: '#94a3b8' }}>
            🗑️
          </div>
          <div>
            <div className="pill-card-num">{counts.deleted || 0}</div>
            <div className="pill-card-label">Recently Deleted</div>
          </div>
        </div>
      </div>

      {/* Tabs & Filter Bar */}
      <div className="verify-toolbar glass-panel">
        <div className="verify-tabs">
          <button
            type="button"
            className={`tab-btn ${activeTab === 'review' ? 'active' : ''}`}
            onClick={() => setActiveTab('review')}
            id="tab-review-queue"
          >
            Review Queue ({reviewNeededCount})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'all' ? 'active' : ''}`}
            onClick={() => setActiveTab('all')}
            id="tab-all-txs"
          >
            All Active ({counts.all || 0})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'auto' ? 'active' : ''}`}
            onClick={() => setActiveTab('auto')}
            id="tab-auto"
          >
            Auto Resolved ({counts.auto || 0})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'duplicate' ? 'active' : ''}`}
            onClick={() => setActiveTab('duplicate')}
            id="tab-duplicate"
          >
            Duplicates ({counts.duplicate || 0})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'deleted' ? 'active' : ''}`}
            onClick={() => setActiveTab('deleted')}
            id="tab-deleted"
            style={{ color: activeTab === 'deleted' ? '#f87171' : undefined }}
          >
            🗑️ Recently Deleted ({counts.deleted || 0})
          </button>
        </div>

        <div className="search-box">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            placeholder="Search payee, remark, category..."
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

      {/* ── Sticky Bulk Action Bar ── */}
      {selectedIds.size > 0 && (
        <div className="bulk-action-bar glass-panel animate-fade-in">
          <div className="bulk-action-info">
            <span className="bulk-count-badge">{selectedIds.size}</span>
            <span>transaction(s) selected</span>
          </div>
          <div className="bulk-action-buttons">
            {activeTab === 'deleted' ? (
              <button
                type="button"
                className="btn-bulk-restore"
                onClick={handleBulkRestore}
                id="btn-bulk-restore"
              >
                🔄 Restore Selected
              </button>
            ) : (
              <button
                type="button"
                className="btn-bulk-delete"
                onClick={handleRequestBulkDelete}
                id="btn-bulk-delete"
              >
                🗑️ Delete Selected
              </button>
            )}
            <button
              type="button"
              className="btn-bulk-cancel"
              onClick={() => setSelectedIds(new Set())}
            >
              Deselect
            </button>
          </div>
        </div>
      )}

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
      ) : filteredTransactions.length === 0 ? (
        <div className="empty-state glass-panel">
          <div className="empty-icon">
            {activeTab === 'deleted' ? '🗑️' : activeTab === 'duplicate' ? '✨' : '🎉'}
          </div>
          <h3 className="empty-title">
            {activeTab === 'deleted'
              ? 'Trash is Empty'
              : activeTab === 'duplicate'
              ? 'No Duplicates Found'
              : 'All Caught Up!'}
          </h3>
          <p className="empty-description">
            {activeTab === 'deleted'
              ? 'No recently deleted transactions. Any deleted expenses will appear here for recovery.'
              : activeTab === 'duplicate'
              ? 'No duplicate transactions were detected in your statement uploads.'
              : 'There are no transactions matching this filter.'}
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
              onClick={() => setActiveTab('review')}
            >
              Back to Review
            </button>
          </div>
        </div>
      ) : activeTab === 'review' ? (
        /* ── Grouped Review Queue View ── */
        <div className="payee-groups-list">
          {groupedPayees.map((group) => {
            const isApplyToAll = applyToAllMap[group.key] !== false;
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

                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                    <label className="apply-to-all-toggle">
                      <input
                        type="checkbox"
                        checked={isApplyToAll}
                        onChange={() => toggleApplyToAll(group.key)}
                        id={`apply-all-checkbox-${group.key}`}
                      />
                      <span className="toggle-text">
                        Apply to all ({group.transactions.length})
                      </span>
                    </label>
                  </div>
                </div>

                {/* AI Suggestion Strip */}
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

                {/* Transactions Table */}
                <div className="tx-table-wrapper">
                  <table className="tx-table">
                    <thead>
                      <tr>
                        <th style={{ width: '40px' }}>
                          <input
                            type="checkbox"
                            checked={group.transactions.every((t) => selectedIds.has(t.id))}
                            onChange={() => {
                              const allInGroup = group.transactions.every((t) => selectedIds.has(t.id));
                              setSelectedIds((prev) => {
                                const next = new Set(prev);
                                group.transactions.forEach((t) => {
                                  if (allInGroup) next.delete(t.id);
                                  else next.add(t.id);
                                });
                                return next;
                              });
                            }}
                          />
                        </th>
                        <th>Date</th>
                        <th>Remark / Raw Description</th>
                        <th>Confidence</th>
                        <th>Status</th>
                        <th style={{ textAlign: 'right' }}>Amount</th>
                        <th style={{ width: '50px', textAlign: 'center' }}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.transactions.map((tx) => (
                        <tr key={tx.id} className="tx-row">
                          <td>
                            <input
                              type="checkbox"
                              checked={selectedIds.has(tx.id)}
                              onChange={() => handleToggleSelect(tx.id)}
                            />
                          </td>
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
                          <td style={{ textAlign: 'center' }}>
                            <button
                              type="button"
                              className="btn-row-delete"
                              title="Delete Transaction"
                              onClick={() => handleRequestDelete(tx)}
                            >
                              🗑️
                            </button>
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
      ) : (
        /* ── Tabular Ledger View (All Active, Duplicates, Recently Deleted) ── */
        <div className="table-view-card glass-panel">
          <div className="tx-table-wrapper">
            <table className="tx-table">
              <thead>
                <tr>
                  <th style={{ width: '40px' }}>
                    <input
                      type="checkbox"
                      checked={
                        filteredTransactions.length > 0 &&
                        selectedIds.size === filteredTransactions.length
                      }
                      onChange={handleSelectAll}
                      title="Select All"
                    />
                  </th>
                  <th>Date</th>
                  <th>Payee / Description</th>
                  <th>Category</th>
                  <th>Source / Mode</th>
                  <th>Status</th>
                  <th style={{ textAlign: 'right' }}>Amount</th>
                  <th style={{ width: '90px', textAlign: 'center' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredTransactions.map((tx) => (
                  <tr
                    key={tx.id}
                    className={`tx-row ${selectedIds.has(tx.id) ? 'tx-row-selected' : ''}`}
                  >
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(tx.id)}
                        onChange={() => handleToggleSelect(tx.id)}
                      />
                    </td>
                    <td className="tx-date">
                      {tx.date
                        ? new Date(tx.date).toLocaleDateString('en-IN', {
                            day: 'numeric',
                            month: 'short',
                            year: 'numeric',
                          })
                        : '—'}
                    </td>
                    <td className="tx-payee-col">
                      <div className="payee-row-main">
                        <strong className="tx-payee-name">
                          {tx.payee_name || tx.upi_id || 'Unknown Payee'}
                        </strong>
                        {tx.is_duplicate && (
                          <span className="badge-duplicate">⚠️ Duplicate</span>
                        )}
                      </div>
                      <span className="tx-remark-sub">
                        {tx.remark || tx.upi_id || ''}
                      </span>
                    </td>
                    <td>
                      <span className="tx-category-badge">
                        {tx.category || 'Uncategorized'}
                      </span>
                    </td>
                    <td>
                      <span className="tx-source-pill">
                        {tx.payment_mode || 'UPI'} • {tx.source || 'statement'}
                      </span>
                    </td>
                    <td>
                      <span className={`status-pill status-${tx.status}`}>
                        {tx.status}
                      </span>
                    </td>
                    <td className="tx-amount-cell">
                      <span className={tx.is_debit ? 'amt-debit' : 'amt-credit'}>
                        {tx.is_debit ? '-' : '+'}₹{parseFloat(tx.amount || 0).toFixed(2)}
                      </span>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {activeTab === 'deleted' ? (
                        <button
                          type="button"
                          className="btn-row-restore"
                          title="Restore Transaction"
                          onClick={() => handleRestore(tx.id)}
                        >
                          🔄 Restore
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn-row-delete"
                          title="Delete Transaction"
                          onClick={() => handleRequestDelete(tx)}
                        >
                          🗑️
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Add Expense Modal ── */}
      <AddExpenseModal
        isOpen={isAddExpenseModalOpen}
        onClose={() => setIsAddExpenseModalOpen(false)}
        onExpenseAdded={fetchTransactions}
      />

      {/* ── Delete Confirmation Modal ── */}
      <DeleteConfirmationModal
        isOpen={deleteModal.isOpen}
        onClose={() => setDeleteModal({ isOpen: false, item: null, isBulk: false, loading: false })}
        onConfirm={handleConfirmDelete}
        title={deleteModal.isBulk ? 'Delete Selected Transactions' : 'Delete Transaction'}
        itemCount={deleteModal.isBulk ? selectedIds.size : 1}
        message={
          deleteModal.item
            ? `Delete transaction of ₹${parseFloat(deleteModal.item.amount || 0).toFixed(2)} to "${deleteModal.item.payee_name || deleteModal.item.remark || 'Unknown'}"?`
            : undefined
        }
        isLoading={deleteModal.loading}
      />
    </div>
  );
}
