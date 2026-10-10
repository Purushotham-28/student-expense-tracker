import React, { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { statementService } from '../api';
import './Upload.css';

const ACCEPTED_TYPES = [
  'application/pdf',
  'text/csv',
  'application/vnd.ms-excel',
  'application/octet-stream',
];

const ACCEPTED_EXTENSIONS = ['.pdf', '.csv'];

function getFileIcon(filename) {
  if (!filename) return '📄';
  const ext = filename.split('.').pop().toLowerCase();
  return ext === 'pdf' ? '📕' : '📊';
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export default function Upload() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [file, setFile] = useState(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadState, setUploadState] = useState('idle'); // idle | uploading | success | error
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const validateFile = useCallback((f) => {
    const ext = '.' + f.name.split('.').pop().toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setError('Unsupported file type. Please upload a PDF or CSV bank statement.');
      return false;
    }
    if (f.size > 20 * 1024 * 1024) {
      setError('File too large. Maximum allowed size is 20 MB.');
      return false;
    }
    setError('');
    return true;
  }, []);

  const handleFileSelect = useCallback((f) => {
    if (f && validateFile(f)) {
      setFile(f);
      setUploadState('idle');
      setResult(null);
      setError('');
    }
  }, [validateFile]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    handleFileSelect(droppedFile);
  }, [handleFileSelect]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleInputChange = (e) => {
    const selected = e.target.files[0];
    handleFileSelect(selected);
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploadState('uploading');
    setProgress(0);
    setError('');

    // Simulate smooth progress
    const progressInterval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 90) {
          clearInterval(progressInterval);
          return 90;
        }
        return prev + Math.random() * 15;
      });
    }, 200);

    try {
      const data = await statementService.upload(file);
      clearInterval(progressInterval);
      setProgress(100);
      setUploadState('success');
      setResult(data);
    } catch (err) {
      clearInterval(progressInterval);
      setProgress(0);
      setUploadState('error');
      const msg =
        err.response?.data?.error ||
        err.response?.data?.detail ||
        err.message ||
        'Upload failed. Please try again.';
      setError(msg);
    }
  };

  const handleReset = () => {
    setFile(null);
    setUploadState('idle');
    setProgress(0);
    setResult(null);
    setError('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="upload-page">
      <div className="page-header">
        <div>
          <h2 className="page-title">Upload Bank Statement</h2>
          <p className="page-description">
            Import your bank or UPI statement (PDF or CSV) to automatically extract transactions.
          </p>
        </div>
      </div>

      <div className="upload-container glass-panel">
        {/* Upload Zone */}
        {uploadState !== 'success' && (
          <div
            className={`upload-dropzone ${isDragOver ? 'drag-over' : ''} ${file ? 'has-file' : ''} ${uploadState === 'error' ? 'has-error' : ''}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => !file && fileInputRef.current?.click()}
            id="upload-dropzone"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.csv"
              onChange={handleInputChange}
              className="upload-file-input"
              id="file-input"
            />

            {!file ? (
              <div className="dropzone-content">
                <div className="dropzone-icon-ring">
                  <div className="dropzone-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                  </div>
                </div>
                <h3 className="dropzone-title">Drop your statement here</h3>
                <p className="dropzone-subtitle">or click to browse files</p>
                <div className="dropzone-formats">
                  <span className="format-badge">PDF</span>
                  <span className="format-badge">CSV</span>
                </div>
                <p className="dropzone-limit">Maximum file size: 20 MB</p>
              </div>
            ) : (
              <div className="file-preview">
                <div className="file-icon-large">{getFileIcon(file.name)}</div>
                <div className="file-details">
                  <span className="file-name">{file.name}</span>
                  <span className="file-size">{formatBytes(file.size)}</span>
                </div>
                <button
                  type="button"
                  className="file-remove-btn"
                  onClick={(e) => { e.stopPropagation(); handleReset(); }}
                  title="Remove file"
                  id="btn-remove-file"
                >
                  ✕
                </button>
              </div>
            )}
          </div>
        )}

        {/* Progress Bar */}
        {uploadState === 'uploading' && (
          <div className="upload-progress-section">
            <div className="progress-header">
              <span className="progress-label">
                <span className="btn-spinner" /> Parsing statement…
              </span>
              <span className="progress-percent">{Math.round(progress)}%</span>
            </div>
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="progress-hint">Extracting transactions from your statement</p>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="upload-alert alert-error" id="upload-error">
            <span className="alert-icon">⚠️</span>
            <span>{error}</span>
          </div>
        )}

        {/* Success Result */}
        {uploadState === 'success' && result && (
          <div className="upload-result" id="upload-result">
            <div className="result-hero">
              <div className="result-icon-ring success-ring">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
              </div>
              <h3 className="result-title">Statement Parsed Successfully!</h3>
              <p className="result-subtitle">
                Your bank statement has been processed and transactions are ready for review.
              </p>
            </div>

            <div className="result-stats">
              <div className="result-stat-card">
                <div className="stat-icon" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#818cf8' }}>📋</div>
                <div className="stat-content">
                  <span className="stat-value" id="stat-total-txns">{result.summary?.total_transactions ?? 0}</span>
                  <span className="stat-label">Transactions Found</span>
                </div>
              </div>

              <div className="result-stat-card">
                <div className="stat-icon" style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#34d399' }}>📅</div>
                <div className="stat-content">
                  <span className="stat-value">
                    {result.summary?.date_from
                      ? new Date(result.summary.date_from).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
                      : '—'}
                  </span>
                  <span className="stat-label">From Date</span>
                </div>
              </div>

              <div className="result-stat-card">
                <div className="stat-icon" style={{ background: 'rgba(168, 85, 247, 0.15)', color: '#c084fc' }}>📅</div>
                <div className="stat-content">
                  <span className="stat-value">
                    {result.summary?.date_to
                      ? new Date(result.summary.date_to).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
                      : '—'}
                  </span>
                  <span className="stat-label">To Date</span>
                </div>
              </div>

              <div className="result-stat-card">
                <div className="stat-icon" style={{ background: 'rgba(6, 182, 212, 0.15)', color: '#22d3ee' }}>🏦</div>
                <div className="stat-content">
                  <span className="stat-value">{result.summary?.bank_format?.replace(/_/g, ' ').toUpperCase() || '—'}</span>
                  <span className="stat-label">Detected Format</span>
                </div>
              </div>
            </div>

            {/* Results summary banner */}
            {result.summary && (
              <div className="confidence-summary-banner" id="confidence-summary-banner">
                <div className="summary-banner-content">
                  <div className="summary-banner-title">
                    ✨ <strong>{result.summary.auto_count ?? 0} auto-categorized</strong>,{' '}
                    <strong>{result.summary.verify_count ?? 0} to verify</strong>,{' '}
                    <strong>{result.summary.pending_count ?? 0} need your help</strong>
                  </div>
                  <p className="summary-banner-desc">
                    Transactions have been routed by confidence. Review uncertain items to personalize future categorizations.
                  </p>
                </div>
                <div className="summary-banner-pills">
                  <span className="summary-pill pill-auto">
                    ● {result.summary.auto_count ?? 0} Auto (&ge;80%)
                  </span>
                  <span className="summary-pill pill-verify">
                    ● {result.summary.verify_count ?? 0} To Verify (50-80%)
                  </span>
                  <span className="summary-pill pill-pending">
                    ● {result.summary.pending_count ?? 0} Need Help (&lt;50%)
                  </span>
                </div>
                {((result.summary.verify_count ?? 0) + (result.summary.pending_count ?? 0)) > 0 && (
                  <button
                    type="button"
                    className="btn-review-cta"
                    onClick={() => navigate('/verify')}
                    id="btn-review-uncertain-txns"
                  >
                    Review {(result.summary.verify_count ?? 0) + (result.summary.pending_count ?? 0)} Transactions Now →
                  </button>
                )}
              </div>
            )}

            <div className="result-actions">
              <button
                type="button"
                className="btn-primary result-btn"
                onClick={() => navigate('/')}
                id="btn-view-dashboard"
              >
                View Dashboard →
              </button>
              <button
                type="button"
                className="btn-secondary result-btn"
                onClick={handleReset}
                id="btn-upload-another"
              >
                Upload Another
              </button>
            </div>
          </div>
        )}

        {/* Upload Button */}
        {file && uploadState === 'idle' && (
          <button
            type="button"
            className="btn-primary upload-submit-btn"
            onClick={handleUpload}
            id="btn-upload-statement"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            Upload & Parse Statement
          </button>
        )}
      </div>

      {/* Past Statements */}
      <PastStatements />
    </div>
  );
}

function PastStatements() {
  const [statements, setStatements] = useState([]);
  const [loading, setLoading] = useState(true);

  React.useEffect(() => {
    statementService.list()
      .then((data) => {
        setStatements(Array.isArray(data) ? data : data.results || []);
      })
      .catch(() => setStatements([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="past-statements glass-panel">
        <h3 className="chart-title">Previous Uploads</h3>
        <p style={{ color: 'var(--text-muted)', padding: '1rem 0' }}>Loading…</p>
      </div>
    );
  }

  if (statements.length === 0) {
    return null; // Don't show section if no past uploads
  }

  return (
    <div className="past-statements glass-panel">
      <div className="chart-header">
        <h3 className="chart-title">Previous Uploads</h3>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{statements.length} statement(s)</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="transaction-table">
          <thead>
            <tr>
              <th>File</th>
              <th>Format</th>
              <th>Transactions</th>
              <th>Date Range</th>
              <th>Status</th>
              <th>Uploaded</th>
            </tr>
          </thead>
          <tbody>
            {statements.map((stmt) => (
              <tr key={stmt.id}>
                <td style={{ fontWeight: 600 }}>
                  <span style={{ marginRight: '0.5rem' }}>{getFileIcon(stmt.original_filename)}</span>
                  {stmt.original_filename}
                </td>
                <td>
                  <span className="format-badge">{stmt.bank_format?.replace(/_/g, ' ').toUpperCase() || '—'}</span>
                </td>
                <td style={{ fontWeight: 700, color: '#fff' }}>{stmt.transaction_count}</td>
                <td style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                  {stmt.date_from && stmt.date_to
                    ? `${new Date(stmt.date_from).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })} — ${new Date(stmt.date_to).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}`
                    : '—'}
                </td>
                <td>
                  <span className={`status-badge status-${stmt.status}`}>
                    {stmt.status}
                  </span>
                </td>
                <td style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  {new Date(stmt.uploaded_at).toLocaleDateString('en-IN', {
                    day: 'numeric', month: 'short', year: 'numeric',
                    hour: '2-digit', minute: '2-digit',
                  })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
