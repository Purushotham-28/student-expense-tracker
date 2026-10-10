import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation, useNavigate } from 'react-router-dom';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import { checkApiHealth, authService } from './api';
import ProtectedRoute from './components/ProtectedRoute';
import BudgetLimitModal from './components/BudgetLimitModal';
import Login from './pages/Login';
import Register from './pages/Register';
import Upload from './pages/Upload';
import './App.css';

// Initial sample transactions
const INITIAL_EXPENSES = [
  { id: 1, title: 'Campus Bookstore (Textbooks)', category: 'Academic', amount: 145.00, date: '2026-10-01', method: 'Debit Card' },
  { id: 2, title: 'Trader Joe’s Groceries', category: 'Food & Dining', amount: 62.40, date: '2026-10-02', method: 'Apple Pay' },
  { id: 3, title: 'Monthly Metro Pass', category: 'Transportation', amount: 48.00, date: '2026-10-02', method: 'Student Card' },
  { id: 4, title: 'Campus Coffee & Snacks', category: 'Food & Dining', amount: 14.50, date: '2026-10-03', method: 'Cash' },
  { id: 5, title: 'High-Speed Dorm WiFi Share', category: 'Utilities', amount: 35.00, date: '2026-10-04', method: 'Online Transfer' },
];

const MONTHLY_TREND = [
  { day: 'Sep 28', spend: 28 },
  { day: 'Sep 30', spend: 45 },
  { day: 'Oct 01', spend: 145 },
  { day: 'Oct 02', spend: 110.4 },
  { day: 'Oct 03', spend: 14.5 },
  { day: 'Oct 04', spend: 35 },
];

const CATEGORY_COLORS = {
  'Food & Dining': '#6366f1',
  'Academic': '#a855f7',
  'Transportation': '#06b6d4',
  'Utilities': '#10b981',
  'Leisure': '#f59e0b',
  'Health': '#ec4899',
};

// Navigation Bar
function Navigation({ apiStatus, userProfile, onLogout }) {
  const location = useLocation();
  const isAuth = authService.isAuthenticated();

  return (
    <header className="navbar">
      <div className="brand-section">
        <div className="brand-icon">₹</div>
        <div>
          <h1 className="brand-title">Student Expense Tracker</h1>
          <p className="brand-subtitle">Campus Budget & Spending Analytics</p>
        </div>
      </div>

      {isAuth && (
        <nav className="nav-links">
          <Link to="/" className={`nav-item ${location.pathname === '/' ? 'active' : ''}`} id="nav-dashboard">
            Dashboard
          </Link>
          <Link to="/upload" className={`nav-item ${location.pathname === '/upload' ? 'active' : ''}`} id="nav-upload">
            Upload
          </Link>
          <Link to="/expenses" className={`nav-item ${location.pathname === '/expenses' ? 'active' : ''}`} id="nav-expenses">
            Expenses
          </Link>
          <Link to="/analytics" className={`nav-item ${location.pathname === '/analytics' ? 'active' : ''}`} id="nav-analytics">
            Analytics
          </Link>
        </nav>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
        <div className={`api-badge ${apiStatus.connected ? 'badge-connected' : 'badge-disconnected'}`} id="api-status-badge">
          <span className="pulse-dot"></span>
          <span>{apiStatus.connected ? 'API Online' : 'API Offline'}</span>
        </div>

        {isAuth ? (
          <div className="user-menu">
            <div className="user-pill" title={`Roll No: ${userProfile?.college_roll_number || 'N/A'}`}>
              <div className="user-avatar-mini">
                {(userProfile?.username || 'S')[0].toUpperCase()}
              </div>
              <span>{userProfile?.username || 'Student'}</span>
              {userProfile?.college_roll_number && (
                <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>
                  ({userProfile.college_roll_number})
                </span>
              )}
            </div>
            <button type="button" onClick={onLogout} className="btn-logout" id="btn-logout" title="Sign out">
              Logout
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <Link to="/login" className="btn-secondary" style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem' }}>
              Login
            </Link>
            <Link to="/register" className="btn-primary" style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem' }}>
              Register
            </Link>
          </div>
        )}
      </div>
    </header>
  );
}

// Dashboard View
function Dashboard({ expenses, onAddExpense, userProfile, onOpenBudgetModal }) {
  const [formData, setFormData] = useState({
    title: '',
    category: 'Food & Dining',
    amount: '',
    date: new Date().toISOString().split('T')[0],
    method: 'Debit Card',
  });

  const totalSpent = expenses.reduce((sum, item) => sum + parseFloat(item.amount || 0), 0);
  const monthlyAllowance = parseFloat(userProfile?.monthly_budget_limit || 800.00);
  const remainingBudget = Math.max(0, monthlyAllowance - totalSpent);
  const percentUsed = monthlyAllowance > 0 ? ((totalSpent / monthlyAllowance) * 100).toFixed(1) : 0;
  const avgDaily = (totalSpent / (new Date().getDate() || 1)).toFixed(2);

  const categoryMap = {};
  expenses.forEach((item) => {
    categoryMap[item.category] = (categoryMap[item.category] || 0) + parseFloat(item.amount);
  });
  const pieData = Object.entries(categoryMap).map(([name, value]) => ({
    name,
    value: parseFloat(value.toFixed(2)),
  }));

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.title || !formData.amount) return;
    onAddExpense({
      ...formData,
      id: Date.now(),
      amount: parseFloat(formData.amount),
    });
    setFormData({
      title: '',
      category: 'Food & Dining',
      amount: '',
      date: new Date().toISOString().split('T')[0],
      method: 'Debit Card',
    });
  };

  return (
    <div className="dashboard-view">
      <div className="page-header">
        <div>
          <h2 className="page-title">
            Hello, {userProfile?.username || 'Student'}! 👋
          </h2>
          <p className="page-description">
            Roll Number: <strong style={{ color: '#fff' }}>{userProfile?.college_roll_number || 'Pending'}</strong> • 
            {userProfile?.monthly_income ? ` Monthly Income: $${parseFloat(userProfile.monthly_income).toFixed(2)} • ` : ' '}
            Track your semester expenditures and budget targets.
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            onClick={onOpenBudgetModal}
            className="btn-secondary"
            id="btn-edit-budget"
            title="Adjust monthly budget cap"
          >
            ⚙️ Edit Budget Limit (${monthlyAllowance.toFixed(2)})
          </button>
          <a href="#quick-add" className="btn-primary" id="btn-quick-add">
            + Log Expense
          </a>
        </div>
      </div>

      {/* Metrics Row */}
      <section className="metrics-grid">
        <div className="metric-card glass-panel glass-panel-hover">
          <div className="metric-header">
            <span>MONTHLY BUDGET LIMIT</span>
            <div className="metric-icon-wrap" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#818cf8' }}>
              💳
            </div>
          </div>
          <div className="metric-value">${monthlyAllowance.toFixed(2)}</div>
          <div className="metric-footer" style={{ color: 'var(--text-secondary)' }}>
            Target semester spending cap
          </div>
        </div>

        <div className="metric-card glass-panel glass-panel-hover">
          <div className="metric-header">
            <span>TOTAL EXPENDITURE</span>
            <div className="metric-icon-wrap" style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#f87171' }}>
              📉
            </div>
          </div>
          <div className="metric-value">${totalSpent.toFixed(2)}</div>
          <div className="metric-footer" style={{ color: percentUsed > 90 ? 'var(--danger)' : '#f87171' }}>
            {percentUsed}% of monthly limit consumed
          </div>
        </div>

        <div className="metric-card glass-panel glass-panel-hover">
          <div className="metric-header">
            <span>REMAINING BUDGET</span>
            <div className="metric-icon-wrap" style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#34d399' }}>
              💰
            </div>
          </div>
          <div className="metric-value">${remainingBudget.toFixed(2)}</div>
          <div className="metric-footer" style={{ color: '#34d399' }}>
            Available for remaining days
          </div>
        </div>

        <div className="metric-card glass-panel glass-panel-hover">
          <div className="metric-header">
            <span>DAILY AVERAGE</span>
            <div className="metric-icon-wrap" style={{ background: 'rgba(6, 182, 212, 0.15)', color: '#22d3ee' }}>
              ⚡
            </div>
          </div>
          <div className="metric-value">${avgDaily}</div>
          <div className="metric-footer" style={{ color: 'var(--text-secondary)' }}>
            Current daily burn rate
          </div>
        </div>
      </section>

      {/* Visual Analytics with Recharts */}
      <section className="charts-grid">
        <div className="chart-card glass-panel">
          <div className="chart-header">
            <h3 className="chart-title">Spending Trajectory (October)</h3>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Daily Outflow</span>
          </div>
          <div style={{ width: '100%', height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={MONTHLY_TREND} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="spendGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.6}/>
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="day" stroke="#64748b" fontSize={12} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={12} tickLine={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderRadius: '8px',
                    color: '#fff',
                  }}
                  formatter={(val) => [`$${val}`, 'Expenditure']}
                />
                <Area type="monotone" dataKey="spend" stroke="#818cf8" strokeWidth={2} fillOpacity={1} fill="url(#spendGradient)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-card glass-panel">
          <div className="chart-header">
            <h3 className="chart-title">Category Distribution</h3>
          </div>
          <div style={{ width: '100%', height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={CATEGORY_COLORS[entry.name] || '#6366f1'} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderRadius: '8px',
                    color: '#fff',
                  }}
                  formatter={(val) => [`$${val}`, 'Spent']}
                />
                <Legend
                  verticalAlign="bottom"
                  iconType="circle"
                  wrapperStyle={{ fontSize: '0.75rem', paddingTop: '10px' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {/* Transaction List and Quick Entry Form */}
      <section className="bottom-grid">
        <div className="table-card glass-panel">
          <div className="chart-header">
            <h3 className="chart-title">Recent Transactions</h3>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{expenses.length} Records</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="transaction-table">
              <thead>
                <tr>
                  <th>Description</th>
                  <th>Category</th>
                  <th>Date</th>
                  <th>Payment</th>
                  <th style={{ textAlign: 'right' }}>Amount</th>
                </tr>
              </thead>
              <tbody>
                {expenses.map((item) => (
                  <tr key={item.id}>
                    <td style={{ fontWeight: 600 }}>{item.title}</td>
                    <td>
                      <span
                        className="category-tag"
                        style={{
                          backgroundColor: `${CATEGORY_COLORS[item.category] || '#6366f1'}20`,
                          color: CATEGORY_COLORS[item.category] || '#818cf8',
                        }}
                      >
                        {item.category}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-secondary)' }}>{item.date}</td>
                    <td style={{ color: 'var(--text-muted)' }}>{item.method}</td>
                    <td style={{ textAlign: 'right', fontWeight: 700, color: '#f8fafc' }}>
                      -${parseFloat(item.amount).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Add Expense Form */}
        <div className="form-card glass-panel" id="quick-add">
          <h3 className="chart-title" style={{ marginBottom: '1.25rem' }}>Log New Expense</h3>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="expense-title">Expense Title</label>
              <input
                id="expense-title"
                className="form-input"
                type="text"
                placeholder="e.g., Campus Lunch, Textbook Xerox"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="expense-category">Category</label>
              <select
                id="expense-category"
                className="form-select"
                value={formData.category}
                onChange={(e) => setFormData({ ...formData, category: e.target.value })}
              >
                <option value="Food & Dining">Food & Dining</option>
                <option value="Academic">Academic & Books</option>
                <option value="Transportation">Transportation</option>
                <option value="Utilities">Utilities & Rent</option>
                <option value="Leisure">Leisure & Social</option>
                <option value="Health">Health & Fitness</option>
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div className="form-group">
                <label className="form-label" htmlFor="expense-amount">Amount ($)</label>
                <input
                  id="expense-amount"
                  className="form-input"
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="0.00"
                  value={formData.amount}
                  onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="expense-method">Payment Method</label>
                <select
                  id="expense-method"
                  className="form-select"
                  value={formData.method}
                  onChange={(e) => setFormData({ ...formData, method: e.target.value })}
                >
                  <option value="Debit Card">Debit Card</option>
                  <option value="Credit Card">Credit Card</option>
                  <option value="Apple Pay / UPI">Apple Pay / UPI</option>
                  <option value="Cash">Cash</option>
                </select>
              </div>
            </div>

            <button type="submit" className="btn-primary" style={{ width: '100%', justifyContent: 'center' }} id="btn-save-expense">
              Add Expense Record
            </button>
          </form>
        </div>
      </section>
    </div>
  );
}

// Expenses View
function ExpensesView({ expenses }) {
  return (
    <div className="expenses-view">
      <div className="page-header">
        <div>
          <h2 className="page-title">All Expense Entries</h2>
          <p className="page-description">Detailed ledger of student expenditures and receipts.</p>
        </div>
      </div>
      <div className="table-card glass-panel">
        <table className="transaction-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Description</th>
              <th>Category</th>
              <th>Date</th>
              <th>Payment Method</th>
              <th style={{ textAlign: 'right' }}>Amount</th>
            </tr>
          </thead>
          <tbody>
            {expenses.map((item) => (
              <tr key={item.id}>
                <td style={{ color: 'var(--text-muted)' }}>#{item.id}</td>
                <td style={{ fontWeight: 600 }}>{item.title}</td>
                <td>
                  <span
                    className="category-tag"
                    style={{
                      backgroundColor: `${CATEGORY_COLORS[item.category] || '#6366f1'}20`,
                      color: CATEGORY_COLORS[item.category] || '#818cf8',
                    }}
                  >
                    {item.category}
                  </span>
                </td>
                <td style={{ color: 'var(--text-secondary)' }}>{item.date}</td>
                <td style={{ color: 'var(--text-muted)' }}>{item.method}</td>
                <td style={{ textAlign: 'right', fontWeight: 700, color: '#f8fafc' }}>
                  ${parseFloat(item.amount).toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Analytics View
function AnalyticsView({ expenses, userProfile }) {
  const total = expenses.reduce((sum, i) => sum + parseFloat(i.amount), 0);
  const limit = parseFloat(userProfile?.monthly_budget_limit || 800.00);

  return (
    <div className="analytics-view">
      <div className="page-header">
        <div>
          <h2 className="page-title">Budget Insights & Analytics</h2>
          <p className="page-description">AI-ready analytics and category breakdowns for smart financial planning.</p>
        </div>
      </div>
      <div className="glass-panel" style={{ padding: '2rem' }}>
        <h3 style={{ marginBottom: '1rem', color: '#fff' }}>Spending Summary</h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
          Total logged across {expenses.length} transactions is <strong>${total.toFixed(2)}</strong> against your monthly budget cap of <strong>${limit.toFixed(2)}</strong>.
        </p>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <div className="glass-panel" style={{ padding: '1.5rem', flex: 1, minWidth: '220px' }}>
            <h4 style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: '0.5rem' }}>TOP CATEGORY</h4>
            <p style={{ fontSize: '1.25rem', fontWeight: 700, color: '#818cf8' }}>Academic & Books</p>
          </div>
          <div className="glass-panel" style={{ padding: '1.5rem', flex: 1, minWidth: '220px' }}>
            <h4 style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: '0.5rem' }}>MOST FREQUENT</h4>
            <p style={{ fontSize: '1.25rem', fontWeight: 700, color: '#34d399' }}>Food & Dining</p>
          </div>
          <div className="glass-panel" style={{ padding: '1.5rem', flex: 1, minWidth: '220px' }}>
            <h4 style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: '0.5rem' }}>BUDGET HEALTH</h4>
            <p style={{ fontSize: '1.25rem', fontWeight: 700, color: total <= limit ? '#34d399' : '#ef4444' }}>
              {total <= limit ? 'Under Budget' : 'Exceeded Limit'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// Main App Component
export default function App() {
  const [expenses, setExpenses] = useState(INITIAL_EXPENSES);
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
      authService.getProfile().then((profile) => {
        if (isMounted && profile) {
          setUserProfile(profile);
          // Trigger onboarding modal if budget limit is 0 or unconfigured
          if (!profile.is_onboarded || parseFloat(profile.monthly_budget_limit || 0) <= 0) {
            setIsOnboarding(true);
            setIsBudgetModalOpen(true);
          }
        }
      }).catch(() => {
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

  const handleAddExpense = (newExpense) => {
    setExpenses([newExpense, ...expenses]);
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

            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Dashboard
                    expenses={expenses}
                    onAddExpense={handleAddExpense}
                    userProfile={userProfile}
                    onOpenBudgetModal={() => {
                      setIsOnboarding(false);
                      setIsBudgetModalOpen(true);
                    }}
                  />
                </ProtectedRoute>
              }
            />

            <Route
              path="/upload"
              element={
                <ProtectedRoute>
                  <Upload />
                </ProtectedRoute>
              }
            />

            <Route
              path="/expenses"
              element={
                <ProtectedRoute>
                  <ExpensesView expenses={expenses} />
                </ProtectedRoute>
              }
            />

            <Route
              path="/analytics"
              element={
                <ProtectedRoute>
                  <AnalyticsView expenses={expenses} userProfile={userProfile} />
                </ProtectedRoute>
              }
            />
          </Routes>
        </main>

        <BudgetLimitModal
          isOpen={isBudgetModalOpen}
          isOnboarding={isOnboarding}
          currentBudget={userProfile?.monthly_budget_limit || '0.00'}
          onClose={() => setIsBudgetModalOpen(false)}
          onBudgetUpdated={handleBudgetUpdated}
        />

        <footer className="footer">
          <p>© 2026 Student Expense Tracker • Campus Edition</p>
        </footer>
      </div>
    </BrowserRouter>
  );
}
