/**
 * ======================================================
 * PATH: src/layouts/DashboardLayout.jsx
 * ======================================================
 *
 * DASHBOARD LAYOUT (STAFF SHELL)
 * ------------------------------------------------------
 * Adds StoreSelector at layout level so:
 * - Inventory / POS / Sales are always store-scoped
 * - active_store_id is set before critical workflows
 *
 * Store change strategy:
 * - StoreSelector persists localStorage.active_store_id
 * - StoreSelector dispatches "active-store-changed"
 *   detail: { storeId }
 *
 * NOTE:
 * - We DO NOT re-dispatch the event here to avoid duplicates.
 * - This layout listens to the event only to update the UI hint.
 * ======================================================
 */

import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import StoreSelector from "../components/StoreSelector";

export default function DashboardLayout() {
  const { user, role, hasRole, logout } = useAuth();

  const dashboardPath =
    role === "admin"
      ? "/dashboard/admin"
      : role === "pharmacist"
      ? "/dashboard/pharmacist"
      : role === "cashier"
      ? "/dashboard/cashier"
      : "/dashboard/reception";

  const headerLabel =
    role === "admin"
      ? "Admin"
      : role === "pharmacist"
      ? "Staff"
      : role === "cashier"
      ? "Cashier"
      : "Reception";

  const isAdmin = hasRole(["admin"]);
  const isStaff = hasRole(["admin", "pharmacist", "cashier", "reception"]);

  // UI hint only (kept in sync with StoreSelector events)
  const [activeStoreId, setActiveStoreId] = useState(() => {
    return String(localStorage.getItem("active_store_id") || "").trim() || null;
  });

  useEffect(() => {
    const handler = (evt) => {
      const sid = String(evt?.detail?.storeId || "").trim() || null;
      setActiveStoreId(sid);
    };

    window.addEventListener("active-store-changed", handler);
    return () => window.removeEventListener("active-store-changed", handler);
  }, []);

  const userLabel = useMemo(() => {
    return user?.username || user?.email || role || "user";
  }, [user, role]);

  return (
    <div className="min-h-screen flex bg-gray-100">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 text-gray-100 flex flex-col">
        <div className="px-6 py-5 text-xl font-bold border-b border-gray-800">
          {headerLabel}
        </div>

        <nav className="flex-1 px-4 py-6 space-y-2">
          <SidebarLink to={dashboardPath} label="Dashboard" />

          {/* ✅ Staff Inventory (stock/pricing) */}
          <SidebarLink to="/inventory" label="Inventory" />
          <SidebarLink to="/inventory/expiry-alerts" label="Expiry Alerts" />

          {/* ✅ Public Online Store */}
          <SidebarLink to="/store" label="Online Store" />

          <SidebarLink to="/sales" label="Sales" />
          <SidebarLink to="/pos" label="POS" />

          {isStaff && (
            <>
              <div className="pt-4 mt-4 border-t border-gray-800 text-xs uppercase text-gray-400">
                Accounting
              </div>

              <SidebarLink to="/accounting" label="Accounting Overview" />
              <SidebarLink to="/accounting/trial-balance" label="Trial Balance" />
              <SidebarLink to="/accounting/profit-and-loss" label="Profit & Loss" />
              <SidebarLink to="/accounting/balance-sheet" label="Balance Sheet" />

              {isAdmin && (
                <>
                  <SidebarLink
                    to="/accounting/opening-balances"
                    label="Opening Balances"
                  />
                  <SidebarLink to="/accounting/expenses" label="Expenses" />
                  <SidebarLink to="/accounting/close-period" label="Close Period" />
                </>
              )}
            </>
          )}
        </nav>

        <div className="px-4 py-4 border-t border-gray-800 space-y-3">
          <div className="text-xs text-gray-400">
            Logged in as{" "}
            <span className="text-gray-200 font-medium">{userLabel}</span>
          </div>

          <button
            type="button"
            onClick={logout}
            className="w-full px-3 py-2 rounded-md bg-gray-800 hover:bg-gray-700 text-sm"
          >
            Logout
          </button>
        </div>
      </aside>

      {/* Content */}
      <main className="flex-1 overflow-y-auto">
        {/* Top bar */}
        <div className="bg-white border-b px-6 py-4 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <div className="text-sm text-gray-500">Workspace</div>
            <div className="text-lg font-semibold text-gray-900">
              {headerLabel} Dashboard
            </div>
            <div className="text-xs text-gray-500 mt-0.5">
              Active store:{" "}
              <span className="font-semibold text-gray-800">
                {activeStoreId || "— not set —"}
              </span>
            </div>
          </div>

          {/* StoreSelector handles localStorage + event dispatch */}
          <StoreSelector />
        </div>

        {/* Page content */}
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

function SidebarLink({ to, label }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `block px-3 py-2 rounded-md transition ${
          isActive
            ? "bg-gray-800 text-white font-semibold"
            : "text-gray-300 hover:bg-gray-800 hover:text-white"
        }`
      }
    >
      {label}
    </NavLink>
  );
}
