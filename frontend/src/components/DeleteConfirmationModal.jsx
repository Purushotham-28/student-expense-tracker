import React from 'react';
import './DeleteConfirmationModal.css';

export default function DeleteConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title = 'Delete Transaction',
  message,
  itemCount = 1,
  isLoading = false,
  isStatement = false,
}) {
  if (!isOpen) return null;

  return (
    <div className="delete-modal-overlay" onClick={onClose}>
      <div
        className="delete-modal-content glass-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="delete-modal-header">
          <div className="delete-modal-icon-badge">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              <line x1="10" y1="11" x2="10" y2="17" />
              <line x1="14" y1="11" x2="14" y2="17" />
            </svg>
          </div>
          <h2 className="delete-modal-title">{title}</h2>
          <button
            type="button"
            className="delete-modal-close"
            onClick={onClose}
            disabled={isLoading}
            aria-label="Close modal"
          >
            ×
          </button>
        </div>

        <div className="delete-modal-body">
          <p className="delete-modal-desc">
            {message || (
              isStatement
                ? 'Are you sure you want to delete this statement? All transactions extracted from this statement will be removed from your active spending calculations.'
                : itemCount > 1
                ? `Are you sure you want to delete these ${itemCount} selected transactions? They will be removed from your active budgets and runway.`
                : 'Are you sure you want to delete this transaction? It will be removed from your active budgets and runway calculations.'
            )}
          </p>

          {/* Explicit PayeeMapping Preservation Callout */}
          <div className="rule-preservation-callout">
            <div className="callout-icon">🛡️</div>
            <div className="callout-content">
              <strong>Learned Categorization Rules Preserved</strong>
              <p>
                Deleting transactions does <em>not</em> erase your saved payee mappings (e.g. "Ramesh Kumar = Food"). Your learned rules remain safe and will continue auto-categorizing future transactions.
              </p>
            </div>
          </div>

          <div className="soft-delete-hint">
            <span>ℹ️ Soft-deleted: You can restore this anytime from the <strong>Recently Deleted</strong> tab.</span>
          </div>
        </div>

        <div className="delete-modal-actions">
          <button
            type="button"
            className="btn-modal-cancel"
            onClick={onClose}
            disabled={isLoading}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn-modal-danger"
            onClick={onConfirm}
            disabled={isLoading}
            id="btn-confirm-delete"
          >
            {isLoading ? 'Deleting...' : (itemCount > 1 ? `Delete ${itemCount} Items` : 'Confirm Delete')}
          </button>
        </div>
      </div>
    </div>
  );
}
