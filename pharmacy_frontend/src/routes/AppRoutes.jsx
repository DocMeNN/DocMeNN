// src/routes/AppRoutes.jsx

import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import Login from "../features/auth/Login";
import Unauthorized from "../features/auth/Unauthorized";

import AdminDashboard from "../features/admin/AdminDashboard";
import PharmacistDashboard from "../features/pharmacist/PharmacistDashboard";
import CashierDashboard from "../features/cashier/CashierDashboard";

import CustomerHome from "../features/customer/CustomerHome";

import DashboardLayout from "../layouts/DashboardLayout";
import AuthLayout from "../layouts/AuthLayout";
import CustomerLayout from "../layouts/CustomerLayout";

import ProtectedRoute from "./ProtectedRoute";
import { useAuth } from "../context/AuthContext";

/* 🔁 Smart home redirect based on role */
function HomeRedirect() {
  const { user, loading } = useAuth();

  if (loading) return null;

  if (!user) return <Navigate to="/login" replace />;

  switch (user.role) {
    case "admin":
      return <Navigate to="/admin" replace />;
    case "pharmacist":
      return <Navigate to="/pharmacist" replace />;
    case "cashier":
      return <Navigate to="/cashier" replace />;
    default:
      return <Navigate to="/customer" replace />;
  }
}

export default function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>

        {/* Auth */}
        <Route
          path="/login"
          element={
            <AuthLayout>
              <Login />
            </AuthLayout>
          }
        />

        <Route path="/unauthorized" element={<Unauthorized />} />

        {/* Smart Root */}
        <Route path="/" element={<HomeRedirect />} />

        {/* Staff Dashboards */}
        <Route
          path="/admin"
          element={
            <ProtectedRoute allowedRoles={["admin"]}>
              <DashboardLayout>
                <AdminDashboard />
              </DashboardLayout>
            </ProtectedRoute>
          }
        />

        <Route
          path="/pharmacist"
          element={
            <ProtectedRoute allowedRoles={["pharmacist"]}>
              <DashboardLayout>
                <PharmacistDashboard />
              </DashboardLayout>
            </ProtectedRoute>
          }
        />

        <Route
          path="/cashier"
          element={
            <ProtectedRoute allowedRoles={["cashier"]}>
              <DashboardLayout>
                <CashierDashboard />
              </DashboardLayout>
            </ProtectedRoute>
          }
        />

        {/* Customer App */}
        <Route
          path="/customer"
          element={
            <ProtectedRoute allowedRoles={["customer"]}>
              <CustomerLayout>
                <CustomerHome />
              </CustomerLayout>
            </ProtectedRoute>
          }
        />

        {/* Catch-all */}
        <Route path="*" element={<Navigate to="/" replace />} />

      </Routes>
    </BrowserRouter>
  );
}
