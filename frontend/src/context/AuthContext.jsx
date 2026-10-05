/**
 * AuthContext.jsx
 * Provides a React context for authentication state (profile, login, logout).
 * Wrap the app in <AuthProvider> so any component can call useAuth().
 */
import React, { createContext, useContext, useState, useCallback } from 'react';
import { authService } from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [userProfile, setUserProfile] = useState(() => authService.getStoredProfile());

  /** Called after successful login or register. */
  const handleAuthSuccess = useCallback((profile) => {
    setUserProfile(profile);
  }, []);

  /** Clears auth state everywhere. */
  const handleLogout = useCallback(() => {
    authService.logout();
    setUserProfile(null);
  }, []);

  /** Updates profile in context (e.g., after budget update). */
  const updateProfile = useCallback((updatedProfile) => {
    setUserProfile(updatedProfile);
    localStorage.setItem('user_profile', JSON.stringify(updatedProfile));
  }, []);

  const value = {
    userProfile,
    isAuthenticated: authService.isAuthenticated(),
    onAuthSuccess: handleAuthSuccess,
    onLogout: handleLogout,
    updateProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** Hook — must be used inside <AuthProvider>. */
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
