// src/layouts/AccountingLayout.jsx

import { NavLink, Outlet } from "react-router-dom";
import ReportLayout from "../components/layout/ReportLayout";
import { useAuth } from "../context/AuthContext";

export default function AccountingLayout() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  return (
    <ReportLayout>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Accounting</h1>
        <p className="text-gray-600">Financial reports and statements</p>
      </div>

      <div className="flex flex-wrap gap-4 border-b mb-6">
        <TabLink to="" end label="Overview" />
        <TabLink to="trial-balance" label="Trial Balance" />
        <TabLink to="profit-and-loss" label="Profit & Loss" />
        <TabLink to="balance-sheet" label="Balance Sheet" />

        {isAdmin && (
          <>
            <TabLink to="opening-balances" label="Opening Balances" />
            <TabLink to="expenses" label="Expenses" />
            <TabLink to="close-period" label="Close Period" />

            {/* ✅ Phase 1.4 POS Reporting */}
            <TabLink to="pos-reports" label="POS Reports" />
          </>
        )}
      </div>

      <Outlet />
    </ReportLayout>
  );
}

function TabLink({ to, label, end = false }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `pb-2 px-1 border-b-2 transition ${
          isActive
            ? "border-gray-900 text-gray-900 font-semibold"
            : "border-transparent text-gray-500 hover:text-gray-900"
        }`
      }
    >
      {label}
    </NavLink>
  );
}
