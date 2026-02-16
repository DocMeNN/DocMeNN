// src/auth/RequireRole.jsx

import { Navigate } from "react-router-dom";

export default function RequireRole({ allowedRoles, children }) {
  const role = localStorage.getItem("user_role");

  if (!role || !allowedRoles.includes(role)) {
    return <Navigate to="/unauthorized" replace />;
  }

  return children;
}
