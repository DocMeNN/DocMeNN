// src/routes/ProtectedRoute.jsx

import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

/**
 * ======================================================
 * ERROR BOUNDARY (UI SAFETY NET)
 * ------------------------------------------------------
 * Prevents "white screen of death" when a child crashes.
 * React requires class components for error boundaries.
 * ======================================================
 */
class RouteErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Keep it loud in dev, quiet but visible in prod.
    if (import.meta?.env?.DEV) {
      // eslint-disable-next-line no-console
      console.error("[RouteErrorBoundary] Caught error:", error);
      // eslint-disable-next-line no-console
      console.error("[RouteErrorBoundary] Component stack:", info?.componentStack);
    }
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      const message =
        this.state.error?.message ||
        "A page component crashed while rendering.";

      return (
        <div className="rounded-xl border bg-white p-6 max-w-2xl">
          <h2 className="text-lg font-semibold text-gray-900">
            Something went wrong
          </h2>
          <p className="text-sm text-gray-600 mt-2">
            This page hit an unexpected error and couldn’t render safely.
          </p>

          <div className="mt-4 rounded-lg bg-gray-50 border p-3">
            <p className="text-xs font-mono text-gray-700 break-words">
              {message}
            </p>
          </div>

          <div className="mt-5 flex gap-3">
            <button
              type="button"
              onClick={this.handleReload}
              className="px-4 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800"
            >
              Reload page
            </button>

            <button
              type="button"
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2 rounded-md border hover:bg-gray-50"
            >
              Try again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default function ProtectedRoute({ children, allowedRoles }) {
  const { user, loading, isAuthenticated } = useAuth();

  // ⏳ Wait until auth state is fully restored
  if (loading) {
    return (
      <div className="min-h-[200px] flex items-center justify-center text-gray-600">
        Loading session…
      </div>
    );
  }

  // 🔒 Not logged in
  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  // 🎭 Role-based access control
  if (Array.isArray(allowedRoles) && !allowedRoles.includes(user.role)) {
    return <Navigate to="/unauthorized" replace />;
  }

  // ✅ Access granted — but protected against render crashes
  return <RouteErrorBoundary>{children}</RouteErrorBoundary>;
}
