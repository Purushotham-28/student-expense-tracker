import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { authService } from '../api';

/**
 * Register page — students create their account with:
 *  - Username, college roll number (unique), email, password + confirm
 *  - Optional monthly income & budget limit (onboarding modal shown if omitted)
 *  - Per-field inline validation errors from server
 *  - Password strength indicator
 *  - Password / confirm-password visibility toggles
 */

const PASSWORD_STRENGTH = [
  { label: 'Too short', color: '#ef4444', minScore: 0 },
  { label: 'Weak', color: '#f59e0b', minScore: 1 },
  { label: 'Fair', color: '#eab308', minScore: 2 },
  { label: 'Good', color: '#22c55e', minScore: 3 },
  { label: 'Strong', color: '#10b981', minScore: 4 },
];

function scorePassword(pw) {
  if (!pw) return 0;
  let score = 0;
  if (pw.length >= 8) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^a-zA-Z0-9]/.test(pw)) score++;
  return score;
}

export default function Register({ onAuthSuccess }) {
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    college_roll_number: '',
    monthly_income: '',
    monthly_budget_limit: '',
  });

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [generalError, setGeneralError] = useState('');
  const [loading, setLoading] = useState(false);

  const pwScore = scorePassword(formData.password);
  const pwStrength = PASSWORD_STRENGTH[Math.min(pwScore, PASSWORD_STRENGTH.length - 1)];

  const handleChange = (field) => (e) => {
    setFormData((prev) => ({ ...prev, [field]: e.target.value }));
    // Clear the error for this field when user starts typing
    if (fieldErrors[field]) {
      setFieldErrors((prev) => { const next = { ...prev }; delete next[field]; return next; });
    }
  };

  const validate = () => {
    const errors = {};
    const un = formData.username.trim();
    if (!un) errors.username = 'Username is required.';
    else if (un.length < 3) errors.username = 'Username must be at least 3 characters.';
    else if (!/^[a-zA-Z0-9_]+$/.test(un)) errors.username = 'Only letters, numbers, and underscores allowed.';

    if (!formData.email.trim()) errors.email = 'Email address is required.';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) errors.email = 'Enter a valid email address.';

    const roll = formData.college_roll_number.trim();
    if (!roll) errors.college_roll_number = 'College roll number is required.';

    if (!formData.password) errors.password = 'Password is required.';
    else if (formData.password.length < 6) errors.password = 'Password must be at least 6 characters.';

    if (!formData.confirmPassword) {
      errors.confirmPassword = 'Please confirm your password.';
    } else if (formData.password !== formData.confirmPassword) {
      errors.confirmPassword = 'Passwords do not match.';
    }

    return errors;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setGeneralError('');

    const clientErrors = validate();
    if (Object.keys(clientErrors).length > 0) {
      setFieldErrors(clientErrors);
      return;
    }

    setLoading(true);
    try {
      const payload = {
        username: formData.username.trim(),
        email: formData.email.trim().toLowerCase(),
        password: formData.password,
        college_roll_number: formData.college_roll_number.trim(),
        monthly_income: formData.monthly_income ? parseFloat(formData.monthly_income) : null,
        monthly_budget_limit: formData.monthly_budget_limit
          ? parseFloat(formData.monthly_budget_limit)
          : 0.00,
      };

      const data = await authService.register(payload);
      if (onAuthSuccess) onAuthSuccess(data.profile);
      navigate('/', { replace: true });
    } catch (err) {
      const responseData = err.response?.data;
      if (responseData?.details) {
        const mapped = {};
        for (const [key, msgs] of Object.entries(responseData.details)) {
          mapped[key] = Array.isArray(msgs) ? msgs[0] : String(msgs);
        }
        setFieldErrors(mapped);
      } else {
        setGeneralError(
          responseData?.error || 'Registration failed. Please check your information.'
        );
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page-container">
      <div className="auth-card glass-panel" style={{ maxWidth: '540px' }}>
        {/* Header */}
        <div className="auth-header">
          <div className="auth-icon-badge">📝</div>
          <h2 className="auth-title">Create Student Account</h2>
          <p className="auth-subtitle">
            Register to track allowances, set spending caps, and visualize college expenses
          </p>
        </div>

        {/* General error */}
        {generalError && (
          <div className="auth-alert alert-error" id="register-error-banner" role="alert">
            <span aria-hidden="true">⚠️</span>
            <span>{generalError}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form" noValidate>
          {/* Row 1: Username + Roll Number */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem' }}>
            <div className="form-group">
              <label className="form-label" htmlFor="reg-username">
                Username <span style={{ color: 'var(--danger)' }}>*</span>
              </label>
              <input
                id="reg-username"
                className={`form-input ${fieldErrors.username ? 'input-error' : ''}`}
                type="text"
                placeholder="e.g., student_john"
                value={formData.username}
                onChange={handleChange('username')}
                autoComplete="username"
                autoFocus
                required
              />
              {fieldErrors.username && (
                <p className="field-error-msg" id="reg-username-error">{fieldErrors.username}</p>
              )}
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="reg-roll">
                College Roll No. <span style={{ color: 'var(--danger)' }}>*</span>
              </label>
              <input
                id="reg-roll"
                className={`form-input ${fieldErrors.college_roll_number ? 'input-error' : ''}`}
                type="text"
                placeholder="e.g., CS-2026-088"
                value={formData.college_roll_number}
                onChange={handleChange('college_roll_number')}
                required
              />
              {fieldErrors.college_roll_number && (
                <p className="field-error-msg" id="reg-roll-error">
                  {fieldErrors.college_roll_number}
                </p>
              )}
            </div>
          </div>

          {/* Email */}
          <div className="form-group">
            <label className="form-label" htmlFor="reg-email">
              College / Personal Email <span style={{ color: 'var(--danger)' }}>*</span>
            </label>
            <input
              id="reg-email"
              className={`form-input ${fieldErrors.email ? 'input-error' : ''}`}
              type="email"
              placeholder="e.g., student@university.edu"
              value={formData.email}
              onChange={handleChange('email')}
              autoComplete="email"
              required
            />
            {fieldErrors.email && (
              <p className="field-error-msg" id="reg-email-error">{fieldErrors.email}</p>
            )}
          </div>

          {/* Password with strength indicator */}
          <div className="form-group">
            <label className="form-label" htmlFor="reg-password">
              Password <span style={{ color: 'var(--danger)' }}>*</span>
            </label>
            <div className="input-icon-wrapper">
              <input
                id="reg-password"
                className={`form-input ${fieldErrors.password ? 'input-error' : ''}`}
                type={showPassword ? 'text' : 'password'}
                placeholder="At least 6 characters"
                value={formData.password}
                onChange={handleChange('password')}
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                className="input-icon-btn"
                id="toggle-reg-password"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? '🙈' : '👁️'}
              </button>
            </div>
            {/* Password strength bar */}
            {formData.password && (
              <div style={{ marginTop: '0.4rem' }}>
                <div style={{ display: 'flex', gap: '4px', marginBottom: '4px' }}>
                  {[1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      style={{
                        flex: 1,
                        height: '3px',
                        borderRadius: '2px',
                        background: i <= pwScore ? pwStrength.color : 'rgba(255,255,255,0.1)',
                        transition: 'background 0.3s ease',
                      }}
                    />
                  ))}
                </div>
                <span style={{ fontSize: '0.72rem', color: pwStrength.color }}>
                  {pwStrength.label}
                </span>
              </div>
            )}
            {fieldErrors.password && (
              <p className="field-error-msg" id="reg-password-error">{fieldErrors.password}</p>
            )}
          </div>

          {/* Confirm Password */}
          <div className="form-group">
            <label className="form-label" htmlFor="reg-confirm-password">
              Confirm Password <span style={{ color: 'var(--danger)' }}>*</span>
            </label>
            <div className="input-icon-wrapper">
              <input
                id="reg-confirm-password"
                className={`form-input ${fieldErrors.confirmPassword ? 'input-error' : ''}`}
                type={showConfirm ? 'text' : 'password'}
                placeholder="Re-enter your password"
                value={formData.confirmPassword}
                onChange={handleChange('confirmPassword')}
                autoComplete="new-password"
                required
              />
              <button
                type="button"
                className="input-icon-btn"
                id="toggle-confirm-password"
                onClick={() => setShowConfirm((v) => !v)}
                aria-label={showConfirm ? 'Hide password' : 'Show password'}
              >
                {showConfirm ? '🙈' : '👁️'}
              </button>
            </div>
            {formData.confirmPassword && formData.password === formData.confirmPassword && (
              <p style={{ fontSize: '0.72rem', color: 'var(--success)', marginTop: '4px' }}>
                ✓ Passwords match
              </p>
            )}
            {fieldErrors.confirmPassword && (
              <p className="field-error-msg" id="reg-confirm-error">{fieldErrors.confirmPassword}</p>
            )}
          </div>

          {/* Optional fields */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.85rem' }}>
            <div className="form-group">
              <label className="form-label" htmlFor="reg-income">
                Monthly Allowance / Income (₹)
              </label>
              <input
                id="reg-income"
                className="form-input"
                type="number"
                step="0.01"
                min="0"
                placeholder="Optional (e.g., 6000)"
                value={formData.monthly_income}
                onChange={handleChange('monthly_income')}
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="reg-budget">
                Monthly Budget Limit (₹)
              </label>
              <input
                id="reg-budget"
                className="form-input"
                type="number"
                step="0.01"
                min="0"
                placeholder="Can set later (e.g., 5000)"
                value={formData.monthly_budget_limit}
                onChange={handleChange('monthly_budget_limit')}
              />
            </div>
          </div>

          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '1rem', lineHeight: 1.4 }}>
            💡 Leaving the budget limit blank is fine — you&apos;ll be prompted to set it on first login.
          </p>

          <button
            type="submit"
            className="btn-primary auth-submit-btn"
            disabled={loading}
            id="register-submit-btn"
          >
            {loading ? (
              <>
                <span className="btn-spinner" aria-hidden="true" />
                Registering Account…
              </>
            ) : (
              'Complete Registration'
            )}
          </button>
        </form>

        <div className="auth-footer">
          <p>
            Already have an account?{' '}
            <Link to="/login" className="auth-link" id="link-to-login">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
