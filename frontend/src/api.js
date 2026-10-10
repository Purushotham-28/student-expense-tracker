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
};

export default api;

