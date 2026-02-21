// src/layouts/DashboardLayout.jsx
/**
 * ======================================================
 * PATH: src/layouts/DashboardLayout.jsx
 * ======================================================
 *
 * DASHBOARD LAYOUT (STAFF SHELL)
 * ------------------------------------------------------
 * Mobile-first layout hardening:
 * - Prevent global horizontal overflow (the #1 cause of “zoom to fit”)
 * - Sidebar becomes top drawer strip on mobile (still accessible)
 * - Main area uses min-w-0 so children can shrink (tables/cards stop forcing width)
 * - Page content gets overflow-x-auto so wide reports scroll inside the page
 * - Uses min-h-dvh for better mobile browser behavior
 *
 * Store scope rules unchanged:
 * - StoreSelector persists localStorage.active_store_id
 * - StoreSelector dispatches "active-store-changed"
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
    <div className="min-h-dvh bg-gray-100 flex flex-col md:flex-row max-w-[100vw] overflow-x-hidden min-w-0">
      {/* Sidebar */}
      <aside className="bg-gray-900 text-gray-100 flex flex-col md:w-64 w-full md:h-auto shrink-0 min-w-0">
        <div className="px-4 sm:px-6 py-4 text-lg sm:text-xl font-bold border-b border-gray-800">
          {headerLabel}
        </div>

        {/* On mobile: make nav horizontally scrollable to avoid squeezing/overflow */}
        <nav className="flex-1 px-2 sm:px-4 py-3 sm:py-6 md:space-y-2 flex md:block gap-2 md:gap-0 overflow-x-auto md:overflow-visible">
          <SidebarLink to={dashboardPath} label="Dashboard" />

          <SidebarLink to="/inventory" label="Inventory" />
          <SidebarLink to="/inventory/expiry-alerts" label="Expiry Alerts" />

          <SidebarLink to="/store" label="Online Store" />

          <SidebarLink to="/sales" label="Sales" />
          <SidebarLink to="/pos" label="POS" />

          {isStaff && (
            <>
              <div className="hidden md:block pt-4 mt-4 border-t border-gray-800 text-xs uppercase text-gray-400">
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

        <div className="px-3 sm:px-4 py-3 sm:py-4 border-t border-gray-800 space-y-3">
          <div className="text-xs text-gray-400">
            Logged in as{" "}
            <span className="text-gray-200 font-medium break-words">
              {userLabel}
            </span>
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
      <main className="flex-1 min-w-0 max-w-[100vw] overflow-x-hidden">
        {/* Top bar */}
        <div className="bg-white border-b px-4 sm:px-6 py-4 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 min-w-0">
          <div className="min-w-0">
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
          <div className="min-w-0">
            <StoreSelector />
          </div>
        </div>

        {/* Page content
            - overflow-x-auto: wide tables scroll INSIDE content area
            - min-w-0: prevents child forcing page width
        */}
        <div className="p-4 sm:p-6 min-w-0 overflow-x-auto">
          <div className="min-w-0">
            <Outlet />
          </div>
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
        [
          // Mobile: keep items compact and prevent wrapping that forces width
          "shrink-0 whitespace-nowrap",
          // Desktop: normal block links
          "md:block",
          // Common styling
          "px-3 py-2 rounded-md transition text-sm",
          isActive
            ? "bg-gray-800 text-white font-semibold"
            : "text-gray-300 hover:bg-gray-800 hover:text-white",
        ].join(" ")
      }
    >
      {label}
    </NavLink>
  );
}