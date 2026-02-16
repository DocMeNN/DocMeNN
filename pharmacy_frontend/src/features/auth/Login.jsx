// src/features/auth/Login.jsx

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

function getErrorMessage(err) {
  return (
    err?.response?.data?.detail ||
    err?.response?.data?.error ||
    err?.message ||
    "Login failed"
  );
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const canSubmit =
    form.email.trim().length > 0 && form.password.trim().length > 0 && !loading;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!canSubmit) return;

    setError(null);
    setLoading(true);

    try {
      const user = await login({
        email: form.email.trim(),
        password: form.password,
      });

      // ✅ Redirect to the routes that actually exist in AppRoutes.jsx
      switch (user?.role) {
        case "admin":
          navigate("/dashboard/admin", { replace: true });
          break;
        case "pharmacist":
          navigate("/dashboard/pharmacist", { replace: true });
          break;
        case "cashier":
          navigate("/dashboard/cashier", { replace: true });
          break;
        case "reception":
          navigate("/dashboard/reception", { replace: true });
          break;
        default:
          navigate("/", { replace: true });
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 px-4">
      <form
        className="bg-white p-6 shadow-md rounded-md w-full max-w-sm space-y-4"
        onSubmit={handleSubmit}
      >
        <div className="space-y-1">
          <h2 className="text-2xl font-bold text-center">Login</h2>
          <p className="text-sm text-gray-600 text-center">
            Sign in to continue
          </p>
        </div>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 p-3">
            <p className="text-red-700 text-sm text-center">{error}</p>
          </div>
        )}

        <div>
          <label className="block font-medium text-sm text-gray-700">
            Email
          </label>
          <input
            type="email"
            required
            autoComplete="email"
            className="w-full border px-3 py-2 rounded mt-1"
            value={form.email}
            onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
            disabled={loading}
          />
        </div>

        <div>
          <label className="block font-medium text-sm text-gray-700">
            Password
          </label>
          <input
            type="password"
            required
            autoComplete="current-password"
            className="w-full border px-3 py-2 rounded mt-1"
            value={form.password}
            onChange={(e) =>
              setForm((p) => ({ ...p, password: e.target.value }))
            }
            disabled={loading}
          />
        </div>

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full bg-gray-900 text-white py-2 rounded hover:bg-gray-800 disabled:opacity-50"
        >
          {loading ? "Logging in…" : "Login"}
        </button>
      </form>
    </div>
  );
}
