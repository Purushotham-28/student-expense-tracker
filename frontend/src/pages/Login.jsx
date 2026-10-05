import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { authService } from '../api';

/**
 * Login page — students can sign in with username or email + password.
 * Features:
 *  - Password visibility toggle
 *  - Email-or-username field
 *  - Server-side error display (wrong password, account disabled, etc.)
 *  - Loading state with animated button
 *  - Redirects to the originally intended route after success
 */
export default function Login({ onAuthSuccess }) {
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || '/';

  const [formData, setFormData] = useState({ username: '', password: '' });
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleChange = (field) => (e) => {
    setFormData((prev) => ({ ...prev, [field]: e.target.value }));
    if (error) setError(''); // clear error on edit
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!formData.username.trim()) {
      setError('Please enter your username or email address.');
      return;
    }
    if (!formData.password) {
      setError('Please enter your password.');
      return;
    }

    setLoading(true);
    try {
      const data = await authService.login(formData);
      if (onAuthSuccess) onAuthSuccess(data.profile);
      navigate(from, { replace: true });
    } catch (err) {
      const msg =
        err.response?.data?.error ||
        err.response?.data?.details?.non_field_errors?.[0] ||
        'Invalid credentials. Please verify your details.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page-container">
      <div className="auth-card glass-panel">
        {/* Header */}
        <div className="auth-header">
          <div className="auth-icon-badge">🎓</div>
          <h2 className="auth-title">Student Portal Login</h2>
          <p className="auth-subtitle">
            Access your semester expense ledger and analytics
          </p>
        </div>

        {/* Error banner */}
        {error && (
          <div className="auth-alert alert-error" id="login-error-banner" role="alert">
            <span aria-hidden="true">⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form" noValidate>
          {/* Username / Email */}
          <div className="form-group">
            <label className="form-label" htmlFor="login-username">
              Username or Email
            </label>
            <input
              id="login-username"
              className={`form-input ${error ? 'input-error' : ''}`}
              type="text"
              placeholder="e.g., rahul_sharma or student@campus.edu"
              value={formData.username}
              onChange={handleChange('username')}
              autoComplete="username"
              autoFocus
              required
            />
          </div>

          {/* Password with visibility toggle */}
          <div className="form-group">
            <label className="form-label" htmlFor="login-password">
              Password
            </label>
            <div className="input-icon-wrapper">
              <input
                id="login-password"
                className={`form-input ${error ? 'input-error' : ''}`}
                type={showPassword ? 'text' : 'password'}
                placeholder="Enter your password"
                value={formData.password}
                onChange={handleChange('password')}
                autoComplete="current-password"
                required
              />
              <button
                type="button"
                className="input-icon-btn"
                id="toggle-password-visibility"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                title={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? '🙈' : '👁️'}
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="btn-primary auth-submit-btn"
            disabled={loading}
            id="login-submit-btn"
          >
            {loading ? (
              <>
                <span className="btn-spinner" aria-hidden="true" />
                Authenticating…
              </>
            ) : (
              'Sign In to Dashboard'
            )}
          </button>
        </form>

        <div className="auth-footer">
          <p>
            Don&apos;t have an account?{' '}
            <Link to="/register" className="auth-link" id="link-to-register">
              Register here
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
