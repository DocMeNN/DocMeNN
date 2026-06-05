// src/features/auth/Login.jsx

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    email: "",
    password: "",
  });

  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      // 🔐 Email-based login
      const user = await login(form.email, form.password);

      // 🔀 Redirect based on role
      switch (user.role) {
        case "admin":
          navigate("/admin", { replace: true });
          break;
        case "pharmacist":
          navigate("/pharmacist", { replace: true });
          break;
        case "cashier":
          navigate("/cashier", { replace: true });
          break;
        default:
          navigate("/", { replace: true }); // customer / fallback
      }
    } catch (err) {
      setError("Invalid email or password");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <form
        className="bg-white p-6 shadow-md rounded-md w-96 space-y-4"
        onSubmit={handleSubmit}
      >
        <h2 className="text-2xl font-bold text-center">Login</h2>

        {error && (
          <p className="text-red-600 text-sm text-center">{error}</p>
        )}

        <div>
          <label className="block font-medium">Email</label>
          <input
            type="email"
            required
            className="w-full border px-3 py-2 rounded"
            value={form.email}
            onChange={(e) =>
              setForm({ ...form, email: e.target.value })
            }
          />
        </div>

        <div>
          <label className="block font-medium">Password</label>
          <input
            type="password"
            required
            className="w-full border px-3 py-2 rounded"
            value={form.password}
            onChange={(e) =>
              setForm({ ...form, password: e.target.value })
            }
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Logging in..." : "Login"}
        </button>
      </form>
    </div>
  );
}
