import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { authService } from '../api';

export default function ProtectedRoute({ children }) {
  const location = useLocation();
  const isAuth = authService.isAuthenticated();

  if (!isAuth) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}
