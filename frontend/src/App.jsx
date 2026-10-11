import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation, useNavigate, Navigate } from 'react-router-dom';
import { checkApiHealth, authService } from './api';
import ProtectedRoute from './components/ProtectedRoute';
import BudgetLimitModal from './components/BudgetLimitModal';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Upload from './pages/Upload';
import Verify from './pages/Verify';
import Runway from './pages/Runway';
import Goals from './pages/Goals';
import Profile from './pages/Profile';
import ChatPage from './pages/ChatPage';
import ChatWidget from './components/ChatWidget';
import './App.css';

// ── Simple, Clean Campus Navigation Bar ──
function Navigation({ apiStatus, userProfile, onLogout }) {
  const location = useLocation();
  const isAuth = authService.isAuthenticated();

  const isTransactionsActive =
    location.pathname === '/transactions' || location.pathname === '/verify';

  return (
    <header className="navbar" id="app-navbar">
      <Link to="/" className="brand-section" style={{ textDecoration: 'none' }}>
        <div className="brand-icon">₹</div>
        <div>
          <h1 className="brand-title">Student Expense Tracker</h1>
          <p className="brand-subtitle">Campus Budget & Spending Analytics</p>
        </div>
      </Link>

      {isAuth && (
        <nav className="nav-links" id="main-nav-links">
          <Link
            to="/"
            className={`nav-item ${location.pathname === '/' ? 'active' : ''}`}
            id="nav-dashboard"
          >
            Dashboard
          </Link>
          <Link
            to="/upload"
            className={`nav-item ${location.pathname === '/upload' ? 'active' : ''}`}
            id="nav-upload"
          >
            Upload
          </Link>
          <Link
            to="/transactions"
            className={`nav-item ${isTransactionsActive ? 'active' : ''}`}
            id="nav-transactions"
          >
            Transactions
          </Link>
          <Link
            to="/goals"
            className={`nav-item ${location.pathname === '/goals' ? 'active' : ''}`}
            id="nav-goals"
          >
            Goals
          </Link>
          <Link
            to="/chat"
            className={`nav-item ${location.pathname === '/chat' ? 'active' : ''}`}
            id="nav-chat"
          >
            Chat
          </Link>
          <Link
            to="/profile"
            className={`nav-item ${location.pathname === '/profile' ? 'active' : ''}`}
            id="nav-profile"
          >
            Profile
          </Link>
        </nav>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
        <div
          className={`api-badge ${apiStatus.connected ? 'badge-connected' : 'badge-disconnected'}`}
          id="api-status-badge"
          title={apiStatus.connected ? 'Connected to Django Backend API' : 'Backend API Offline'}
        >
          <span className="pulse-dot"></span>
          <span>{apiStatus.connected ? 'API Online' : 'API Offline'}</span>
        </div>

        {isAuth ? (
          <div className="user-menu">
            <Link
              to="/profile"
              className="user-pill"
              title={`View Profile • Roll No: ${userProfile?.college_roll_number || 'N/A'}`}
              style={{ textDecoration: 'none' }}
              id="user-pill-btn"
            >
              <div className="user-avatar-mini">
                {(userProfile?.username || 'S')[0].toUpperCase()}
              </div>
              <span>{userProfile?.username || 'Student'}</span>
              {userProfile?.college_roll_number && (
                <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>
                  ({userProfile.college_roll_number})
                </span>
              )}
            </Link>
            <button
              type="button"
              onClick={onLogout}
              className="btn-logout"
              id="btn-logout"
              title="Sign out of student account"
            >
              Logout
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Link
              to="/login"
              className="btn-secondary"
              style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem' }}
              id="btn-nav-login"
            >
              Login
            </Link>
            <Link
              to="/register"
              className="btn-primary"
              style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem' }}
              id="btn-nav-register"
            >
              Register
            </Link>
          </div>
        )}
      </div>
    </header>
  );
}

// ── Main App Shell ──
export default function App() {
  const [apiStatus, setApiStatus] = useState({ connected: false, checking: true });
  const [userProfile, setUserProfile] = useState(() => authService.getStoredProfile());
  const [isBudgetModalOpen, setIsBudgetModalOpen] = useState(false);
  const [isOnboarding, setIsOnboarding] = useState(false);

  useEffect(() => {
    let isMounted = true;
    checkApiHealth().then((res) => {
      if (isMounted) {
        setApiStatus({ connected: res.success, checking: false });
      }
    });

    if (authService.isAuthenticated()) {
      authService
        .getProfile()
        .then((profile) => {
          if (isMounted && profile) {
            setUserProfile(profile);
            // Trigger onboarding modal if budget limit is 0 or unconfigured
            if (!profile.is_onboarded || parseFloat(profile.monthly_budget_limit || 0) <= 0) {
              setIsOnboarding(true);
              setIsBudgetModalOpen(true);
            }
          }
        })
        .catch(() => {
          // Handled by 401 interceptor
        });
    }

    return () => {
      isMounted = false;
    };
  }, []);

  const handleAuthSuccess = (profile) => {
    setUserProfile(profile);
    if (!profile.is_onboarded || parseFloat(profile.monthly_budget_limit || 0) <= 0) {
      setIsOnboarding(true);
      setIsBudgetModalOpen(true);
    }
  };

  const handleLogout = () => {
    authService.logout();
    setUserProfile(null);
    window.location.href = '/login';
  };

  const handleBudgetUpdated = (updatedProfile) => {
    setUserProfile(updatedProfile);
    setIsOnboarding(false);
  };

  return (
    <BrowserRouter>
      <div className="app-container">
        <Navigation
          apiStatus={apiStatus}
          userProfile={userProfile}
          onLogout={handleLogout}
        />

        <main className="main-content">
          <Routes>
            <Route
              path="/login"
              element={<Login onAuthSuccess={handleAuthSuccess} />}
            />
            <Route
              path="/register"
              element={<Register onAuthSuccess={handleAuthSuccess} />}
            />

            {/* Phase 9 Unified Dashboard */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Dashboard
                    userProfile={userProfile}
                    onOpenBudgetModal={() => {
                      setIsOnboarding(false);
                      setIsBudgetModalOpen(true);
                    }}
                  />
                </ProtectedRoute>
              }
            />

            {/* Statement Upload */}
            <Route
              path="/upload"
              element={
                <ProtectedRoute>
                  <Upload />
                </ProtectedRoute>
              }
            />

            {/* Transactions & Review Hub */}
            <Route
              path="/transactions"
              element={
                <ProtectedRoute>
                  <Verify />
                </ProtectedRoute>
              }
            />
            <Route
              path="/verify"
              element={
                <ProtectedRoute>
                  <Verify />
                </ProtectedRoute>
              }
            />

            {/* Cash-Flow Runway & What-If Simulator */}
            <Route
              path="/runway"
              element={
                <ProtectedRoute>
                  <Runway />
                </ProtectedRoute>
              }
            />

            {/* Savings Goals */}
            <Route
              path="/goals"
              element={
                <ProtectedRoute>
                  <Goals />
                </ProtectedRoute>
              }
            />

            {/* Full AI Copilot Chat Page */}
            <Route
              path="/chat"
              element={
                <ProtectedRoute>
                  <ChatPage />
                </ProtectedRoute>
              }
            />

            {/* Student Profile & Settings */}
            <Route
              path="/profile"
              element={
                <ProtectedRoute>
                  <Profile
                    userProfile={userProfile}
                    onProfileUpdated={handleBudgetUpdated}
                    onLogout={handleLogout}
                  />
                </ProtectedRoute>
              }
            />

            {/* Fallback to Dashboard */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>

        {/* Global Onboarding & Budget Adjustment Modal */}
        <BudgetLimitModal
          isOpen={isBudgetModalOpen}
          isOnboarding={isOnboarding}
          currentBudget={userProfile?.monthly_budget_limit || '0.00'}
          onClose={() => setIsBudgetModalOpen(false)}
          onBudgetUpdated={handleBudgetUpdated}
        />

        {/* Phase 8 & 9 — AI Financial Copilot Chatbox available throughout the app */}
        <ChatWidget />

        <footer className="footer">
          <p>© 2026 Student Expense Tracker • Campus Edition • Built for Students</p>
        </footer>
      </div>
    </BrowserRouter>
  );
}
