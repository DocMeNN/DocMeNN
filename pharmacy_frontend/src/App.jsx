// src/App.jsx

import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./context/AuthContext";
import AppRoutes from "./routes/AppRoutes";

/**
 * ======================================================
 * PATH: src/App.jsx
 * ======================================================
 *
 * APPLICATION ROOT
 * ------------------------------------------------------
 * - React Query is first-class infrastructure
 * - Single QueryClient for the entire app
 * - Backend remains source of truth
 * - Query cache is cleared on logout (prevents role data bleed)
 * - Global Error Boundary prevents “blank page” crashes
 * ======================================================
 */

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 0,
    },
    mutations: {
      retry: 0,
    },
  },
});

/**
 * ======================================================
 * GLOBAL ERROR BOUNDARY
 * ------------------------------------------------------
 * Prevents white screens when a component crashes at runtime.
 * Shows a friendly fallback with a safe reset action.
 * ======================================================
 */
class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Keep this loud in DEV — helps us fix fast
    // eslint-disable-next-line no-console
    console.error("App crashed:", error);
    // eslint-disable-next-line no-console
    console.error("Component stack:", info?.componentStack);
  }

  handleReset = () => {
    try {
      // Reset react-query cache (prevents “stuck” error state)
      if (this.props.queryClient?.clear) {
        this.props.queryClient.clear();
      } else if (this.props.queryClient?.getQueryCache) {
        this.props.queryClient.getQueryCache().clear();
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.warn("Failed to clear query cache:", e);
    }

    // Force a clean reload (guaranteed reset)
    window.location.href = "/";
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    const message =
      this.state.error?.message ||
      "The app ran into a problem and had to stop rendering.";

    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center p-6">
        <div className="w-full max-w-xl bg-white border rounded-xl p-6">
          <h1 className="text-xl font-semibold text-gray-900">
            Something went wrong
          </h1>
          <p className="text-sm text-gray-600 mt-2">
            A screen crashed while rendering. This is a safe fallback instead of a
            blank page.
          </p>

          <div className="mt-4 rounded-lg border bg-gray-50 p-3">
            <div className="text-xs uppercase tracking-wide text-gray-500">
              Error
            </div>
            <div className="text-sm text-gray-800 mt-1 break-words">
              {message}
            </div>
          </div>

          <div className="mt-5 flex gap-3">
            <button
              type="button"
              onClick={this.handleReset}
              className="px-4 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800 text-sm"
            >
              Reset App
            </button>

            <button
              type="button"
              onClick={() => window.location.reload()}
              className="px-4 py-2 rounded-md border hover:bg-gray-50 text-sm"
            >
              Reload Page
            </button>
          </div>
        </div>
      </div>
    );
  }
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppErrorBoundary queryClient={queryClient}>
        <AuthProvider queryClient={queryClient}>
          <AppRoutes />
        </AuthProvider>
      </AppErrorBoundary>
    </QueryClientProvider>
  );
}
