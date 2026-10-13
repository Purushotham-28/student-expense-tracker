/**
 * api.js — Axios client with JWT auth, auto-refresh, and auth service helpers.
 *
 * Token storage strategy:
 *  - access_token  → localStorage (short-lived, 1 day)
 *  - refresh_token → localStorage (7 days)
 *  - user_profile  → localStorage (cached profile snapshot)
 *
 * Security note: JWTs are stored in localStorage for simplicity in this
 * student project. For production, prefer HttpOnly cookies.
 */
import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// ──────────────────────────────────────────────────────────────────────────────
// Request interceptor — attach Bearer token to every outbound request
// ──────────────────────────────────────────────────────────────────────────────
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ──────────────────────────────────────────────────────────────────────────────
// Response interceptor — auto-refresh on 401, then retry original request once
// ──────────────────────────────────────────────────────────────────────────────
let _isRefreshing = false;
let _refreshQueue = [];

function processQueue(error, token = null) {
  _refreshQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token)));
  _refreshQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    const isAuthEndpoint =
      originalRequest.url.includes('auth/login') ||
      originalRequest.url.includes('auth/register') ||
      originalRequest.url.includes('auth/token/refresh');

    if (error.response?.status === 401 && !isAuthEndpoint && !originalRequest._retry) {
      const refreshToken = localStorage.getItem('refresh_token');

      if (!refreshToken) {
        authService.logout();
        if (window.location.pathname !== '/login' && window.location.pathname !== '/register') {
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }

      if (_isRefreshing) {
        // Queue additional requests while refresh is in flight
        return new Promise((resolve, reject) => {
          _refreshQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        });
      }

      originalRequest._retry = true;
      _isRefreshing = true;

      try {
        const res = await axios.post(`${BASE_URL}auth/token/refresh/`, {
          refresh: refreshToken,
        });
        const newAccessToken = res.data.access;
        localStorage.setItem('access_token', newAccessToken);
        api.defaults.headers.common.Authorization = `Bearer ${newAccessToken}`;
        processQueue(null, newAccessToken);
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        authService.logout();
        if (window.location.pathname !== '/login' && window.location.pathname !== '/register') {
          window.location.href = '/login';
        }
        return Promise.reject(refreshError);
      } finally {
        _isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// ──────────────────────────────────────────────────────────────────────────────
// API Health Check
// ──────────────────────────────────────────────────────────────────────────────
export const checkApiHealth = async () => {
  try {
    const response = await api.get('health/');
    return { success: true, data: response.data };
  } catch (error) {
    return {
      success: false,
      error: error.response?.data || error.message || 'Could not connect to backend',
    };
  }
};

// ──────────────────────────────────────────────────────────────────────────────
// Auth & Profile service
// ──────────────────────────────────────────────────────────────────────────────
export const authService = {
  /**
   * Register a new student account.
   * Stores tokens and profile snapshot on success.
   */
  async register(formData) {
    const response = await api.post('auth/register/', formData);
    if (response.data.tokens) {
      localStorage.setItem('access_token', response.data.tokens.access);
      localStorage.setItem('refresh_token', response.data.tokens.refresh);
      localStorage.setItem('user_profile', JSON.stringify(response.data.profile));
    }
    return response.data;
  },

  /**
   * Log in with username (or email) + password.
   * Stores tokens and profile snapshot on success.
   */
  async login(credentials) {
    const response = await api.post('auth/login/', credentials);
    if (response.data.tokens) {
      localStorage.setItem('access_token', response.data.tokens.access);
      localStorage.setItem('refresh_token', response.data.tokens.refresh);
      localStorage.setItem('user_profile', JSON.stringify(response.data.profile));
    }
    return response.data;
  },

  /** Clear all auth data and redirect to login. */
  logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_profile');
  },

  /** Returns true if an access token is present (not necessarily valid). */
  isAuthenticated() {
    return !!localStorage.getItem('access_token');
  },

  /** Returns the locally cached profile without a network call. */
  getStoredProfile() {
    try {
      const data = localStorage.getItem('user_profile');
      return data ? JSON.parse(data) : null;
    } catch {
      return null;
    }
  },

  /** Fetches the fresh profile from the server and updates the cache. */
  async getProfile() {
    const response = await api.get('profile/');
    localStorage.setItem('user_profile', JSON.stringify(response.data));
    return response.data;
  },

  /**
   * Updates the user's profile fields (budget limit, income, etc.).
   * Normalises the response shape — the server wraps the profile in { profile: {...} }.
   */
  async updateProfile(profileData) {
    const response = await api.put('profile/', profileData);
    const updated = response.data.profile || response.data;
    localStorage.setItem('user_profile', JSON.stringify(updated));
    return updated;
  },
};

// ──────────────────────────────────────────────────────────────────────────────
// Statement Upload & Listing service
// ──────────────────────────────────────────────────────────────────────────────
export const statementService = {
  /**
   * Upload a bank statement file (PDF or CSV) for parsing.
   * Returns the parsed statement summary from the server.
   */
  async upload(file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await api.post('statements/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000, // 2 min timeout for large files
    });
    return response.data;
  },

  /**
   * List the authenticated user's past statement uploads.
   */
  async list() {
    const response = await api.get('statements/');
    return response.data;
  },

  /**
   * Fetch details for a single statement including all transactions.
   */
  async detail(statementId) {
    const response = await api.get(`statements/${statementId}/`);
    return response.data;
  },

  /**
   * Soft-delete a statement and all its transactions.
   */
  async delete(statementId) {
    const response = await api.delete(`statements/${statementId}/`);
    return response.data;
  },

  /**
   * Restore a soft-deleted statement and its transactions.
   */
  async restore(statementId) {
    const response = await api.post(`statements/${statementId}/restore/`);
    return response.data;
  },
};

// ──────────────────────────────────────────────────────────────────────────────
// Transaction & Verification Service
// ──────────────────────────────────────────────────────────────────────────────
export const transactionService = {
  /**
   * List transactions with status filter ('verify', 'pending', 'auto', 'duplicate', 'deleted', 'all')
   * and pagination.
   */
  async list({ status = 'all', page = 1, pageSize = 50 } = {}) {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (page) params.append('page', page);
    if (pageSize) params.append('page_size', pageSize);
    const response = await api.get(`transactions/?${params.toString()}`);
    return response.data;
  },

  /**
   * Confirm category for a transaction and upsert PayeeMapping.
   */
  async confirm(id, { category, applyToAll = true }) {
    const response = await api.post(`transactions/${id}/confirm/`, {
      category,
      apply_to_all: applyToAll,
    });
    return response.data;
  },

  /**
   * Add a manual expense transaction.
   * payload: { amount, category, payee_name, date, payment_mode, save_mapping }
   */
  async addManual(data) {
    const response = await api.post('transactions/manual/', data);
    return response.data;
  },

  /**
   * Re-run hybrid categorization on a transaction.
   */
  async categorize(id) {
    const response = await api.post(`transactions/${id}/categorize/`);
    return response.data;
  },

  /**
   * Soft-delete a single transaction.
   */
  async delete(id) {
    const response = await api.delete(`transactions/${id}/`);
    return response.data;
  },

  /**
   * Restore a soft-deleted transaction.
   */
  async restore(id) {
    const response = await api.post(`transactions/${id}/restore/`);
    return response.data;
  },

  /**
   * Bulk soft-delete transactions by IDs.
   */
  async bulkDelete(ids) {
    const response = await api.post('transactions/bulk-delete/', { ids });
    return response.data;
  },

  /**
   * Bulk restore soft-deleted transactions by IDs.
   */
  async bulkRestore(ids) {
    const response = await api.post('transactions/bulk-restore/', { ids });
    return response.data;
  },
};

// ──────────────────────────────────────────────────────────────────────────────
// Phase 5 — Forecasting & Cash-Flow Runway Service
// ──────────────────────────────────────────────────────────────────────────────
export const planningService = {
  /**
   * Fetch cash-flow runway and 30-day forecast series.
   * Optionally pass custom current_balance override.
   */
  async getRunway(currentBalance) {
    const params = new URLSearchParams();
    if (currentBalance !== undefined && currentBalance !== null && currentBalance !== '') {
      params.append('current_balance', currentBalance);
    }
    const response = await api.get(`planning/runway/?${params.toString()}`);
    return response.data;
  },

  /**
   * Simulate what-if scenario with category spending percentage reductions.
   * payload can be: { adjustments: { Food: 30, Entertainment: 50 }, current_balance: 12000 }
   * or { category: 'Food', reduce_percent: 30 }
   */
  async simulateWhatIf(payload) {
    const response = await api.post('planning/whatif/', payload);
    return response.data;
  },

  /**
   * Phase 7 — Fetch 0-100 Financial Health Score with sub-score components and tips.
   * Optionally accepts { month, year }.
   */
  async getHealthScore({ month, year } = {}) {
    const params = new URLSearchParams();
    if (month) params.append('month', month);
    if (year) params.append('year', year);
    const qs = params.toString() ? `?${params.toString()}` : '';
    const response = await api.get(`planning/health-score/${qs}`);
    return response.data;
  },
};

// ──────────────────────────────────────────────────────────────────────────────
// Phase 6 — Goal Planner & Adaptive Savings Service
// ──────────────────────────────────────────────────────────────────────────────
export const goalsService = {
  /**
   * Fetch all goals and background evaluation summary.
   * status: 'all' | 'active' | 'done'
   */
  async getGoals(status = 'all') {
    const params = new URLSearchParams();
    if (status && status !== 'all') {
      params.append('status', status);
    }
    const response = await api.get(`goals/?${params.toString()}`);
    return response.data;
  },

  /**
   * Create a new savings goal.
   * payload: { name, target_amount, deadline, saved_so_far }
   */
  async createGoal(payload) {
    const response = await api.post('goals/', payload);
    return response.data;
  },

  /**
   * Retrieve goal details.
   */
  async getGoal(id) {
    const response = await api.get(`goals/${id}/`);
    return response.data;
  },

  /**
   * Update goal details.
   */
  async updateGoal(id, payload) {
    const response = await api.patch(`goals/${id}/`, payload);
    return response.data;
  },

  /**
   * Delete a goal.
   */
  async deleteGoal(id) {
    const response = await api.delete(`goals/${id}/`);
    return response.data;
  },

  /**
   * Contribute progress to a goal.
   * payload: { amount: 500 }
   */
  async contribute(id, amount) {
    const response = await api.post(`goals/${id}/contribute/`, { amount });
    return response.data;
  },

  /**
   * Get intelligent discretionary category cut suggestion.
   * Optional goalId to inspect specific goal.
   */
  async getSuggestion(goalId = null) {
    const params = new URLSearchParams();
    if (goalId) {
      params.append('goal_id', goalId);
    }
    const response = await api.get(`goals/suggestion/?${params.toString()}`);
    return response.data;
  },
};

// ──────────────────────────────────────────────────────────────────────────────
// Phase 8 — AI Chatbox (Claude API with Function Calling) Service
// ──────────────────────────────────────────────────────────────────────────────
export const chatService = {
  /**
   * Send a message to AI Copilot. Triggers multi-turn function calling backend loop.
   */
  async sendMessage(message) {
    const response = await api.post('chat/', { message });
    return response.data;
  },

  /**
   * Fetch conversation history.
   */
  async getHistory() {
    const response = await api.get('chat/history/');
    return response.data;
  },

  /**
   * Clear chat history.
   */
  async clearHistory() {
    const response = await api.delete('chat/history/');
    return response.data;
  },
};

// ──────────────────────────────────────────────────────────────────────────────
// Phase 9 & Month Selector — Unified Dashboard Service
// ──────────────────────────────────────────────────────────────────────────────
export const dashboardService = {
  /**
   * Fetch complete demo-ready dashboard summary:
   *  - Budget vs actual this month (or specified month/year)
   *  - Category breakdown & budget alerts (80% and 100% caps)
   *  - Runway forecast & daily burn rate
   *  - Goals progress & velocity check
   *  - Financial Health score card
   *  - Recent transactions & verification pipeline
   */
  async getSummary({ month, year } = {}) {
    const params = new URLSearchParams();
    if (month) params.append('month', month);
    if (year) params.append('year', year);
    const qs = params.toString() ? `?${params.toString()}` : '';
    const response = await api.get(`dashboard/summary/${qs}`);
    return response.data;
  },

  /**
   * Fetch month-scoped category breakdown & budget adherence.
   * e.g. GET /api/dashboard/category-breakdown?month=9&year=2026
   */
  async getCategoryBreakdown({ month, year } = {}) {
    const params = new URLSearchParams();
    if (month) params.append('month', month);
    if (year) params.append('year', year);
    const qs = params.toString() ? `?${params.toString()}` : '';
    const response = await api.get(`dashboard/category-breakdown/${qs}`);
    return response.data;
  },

  /**
   * Fetch available months with actual transactions for the user.
   * Returns: { available_months: ["2026-07", "2026-08", ...], current_month: "2026-10" }
   */
  async getAvailableMonths() {
    const response = await api.get('dashboard/available-months/');
    return response.data;
  },
};

export default api;


