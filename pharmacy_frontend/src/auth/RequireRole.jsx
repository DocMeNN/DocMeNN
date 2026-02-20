/**
 * ======================================================
 * PATH: src/auth/RequireRole.jsx
 * ======================================================
 *
 * REQUIRE ROLE (LEGACY COMPAT WRAPPER)
 * - Uses AuthContext (NOT localStorage)
 * - Normalizes role checks
 * - Shows loading gate while restoring session
 *
 * Note:
 * ProtectedRoute is preferred for routing-level protection.
 * This component is useful for inline gating inside pages/components.
 * ======================================================
 */

import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

function normalizeRole(role) {
  return String(role || "").trim().toLowerCase();
}

export default function RequireRole({ allowedRoles = [], children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-[120px] flex items-center justify-center text-gray-600">
        Loading session…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  const role = normalizeRole(user?.role);
  const allowed = allowedRoles.map(normalizeRole);

  if (allowed.length > 0 && !allowed.includes(role)) {
    return <Navigate to="/unauthorized" replace />;
  }

  return children;
}
