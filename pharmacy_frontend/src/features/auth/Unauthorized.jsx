// src/features/auth/Unauthorized.jsx

import { Link } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function Unauthorized() {
  const { role, isAuthenticated } = useAuth();

  const dashboardPath =
    role === "admin"
      ? "/dashboard/admin"
      : role === "pharmacist"
      ? "/dashboard/pharmacist"
      : role === "cashier"
      ? "/dashboard/cashier"
      : "/dashboard/reception";

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 px-4">
      <div className="w-full max-w-lg bg-white border rounded-xl p-6 shadow-sm space-y-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold text-gray-900">Unauthorized</h1>
          <p className="text-sm text-gray-600">
            You don’t have permission to access this page.
          </p>
        </div>

        <div className="rounded-lg border bg-white p-4">
          <p className="text-sm text-gray-700">
            If you believe this is a mistake, sign in with an account that has
            access or contact your admin.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          {isAuthenticated ? (
            <Link
              to={dashboardPath}
              className="px-4 py-2 rounded-lg bg-gray-900 text-white hover:bg-gray-800"
            >
              Back to Dashboard
            </Link>
          ) : (
            <Link
              to="/login"
              className="px-4 py-2 rounded-lg bg-gray-900 text-white hover:bg-gray-800"
            >
              Go to Login
            </Link>
          )}

          <Link
            to="/"
            className="px-4 py-2 rounded-lg border hover:bg-gray-50"
          >
            Home
          </Link>
        </div>
      </div>
    </div>
  );
}
