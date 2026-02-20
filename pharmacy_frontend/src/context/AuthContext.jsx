/**
 * ======================================================
 * PATH: src/context/AuthContext.jsx
 * ======================================================
 *
 * AUTH CONTEXT — SESSION SOURCE OF TRUTH
 * ------------------------------------------------------
 * Rules:
 * - Tokens live in localStorage (via lib/auth.js)
 * - User object lives ONLY in memory
 * - Backend (/auth/me/) is the authority
 * - Query cache must be cleared on logout
 *
 * Public storefront rule:
 * - When user is browsing /store/... we DO NOT ping /auth/me/
 *   (prevents noisy 401s and keeps public browsing clean)
 * ======================================================
 */

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { login as loginApi, getMe } from "../api/auth.api";
import { getAccessToken, clearTokens } from "../lib/auth";

const AuthContext = createContext(null);

function isPublicStorefrontPath(pathname) {
  const p = String(pathname || "");
  return p === "/store" || p.startsWith("/store/");
}

export function AuthProvider({ children, queryClient }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function restoreSession() {
      const path = window.location?.pathname || "/";
      const onPublicStorefront = isPublicStorefrontPath(path);

      // Public storefront: avoid /me calls (clean AllowAny browsing)
      if (onPublicStorefront) {
        if (mounted) {
          setUser(null);
          setLoading(false);
        }
        return;
      }

      const accessToken = getAccessToken();

      if (!accessToken) {
        if (mounted) {
          setUser(null);
          setLoading(false);
        }
        return;
      }

      try {
        // getMe returns axios response; data is user
        const res = await getMe();
        if (mounted) setUser(res.data);
      } catch (err) {
        // Token invalid/expired → wipe session + clear cache
        clearTokens();
        if (queryClient) queryClient.clear();
        if (mounted) setUser(null);
      } finally {
        if (mounted) setLoading(false);
      }
    }

    restoreSession();

    return () => {
      mounted = false;
    };
  }, [queryClient]);

  const login = async (credentials) => {
    // auth.api.js handles token persistence; returns user profile
    const userData = await loginApi(credentials);
    setUser(userData);
    return userData;
  };

  const logout = () => {
    clearTokens();
    if (queryClient) queryClient.clear();
    setUser(null);

    // If they logged out while on public storefront, keep them in the storefront.
    const path = window.location?.pathname || "/";
    if (isPublicStorefrontPath(path)) {
      window.location.href = "/store";
      return;
    }

    window.location.href = "/login";
  };

  const value = useMemo(() => {
    const role = user?.role || null;

    return {
      user,
      role,
      isAuthenticated: Boolean(user),
      loading,
      login,
      logout,
      hasRole: (allowedRoles = []) => Boolean(role) && allowedRoles.includes(role),
    };
  }, [user, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
