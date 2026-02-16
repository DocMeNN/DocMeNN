// src/components/accounting/AccountingQuickLinks.jsx

import { Link } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

export default function AccountingQuickLinks() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const links = [
    {
      label: "Trial Balance",
      to: "trial-balance",
      hint: "Debits vs credits by account",
      adminOnly: false,
    },
    {
      label: "Profit & Loss",
      to: "profit-and-loss",
      hint: "Income, expenses, net profit",
      adminOnly: false,
    },
    {
      label: "Balance Sheet",
      to: "balance-sheet",
      hint: "Assets, liabilities, equity",
      adminOnly: false,
    },

    // Admin-only posting actions
    {
      label: "Opening Balances",
      to: "opening-balances",
      hint: "Set starting position",
      adminOnly: true,
    },
    {
      label: "Expenses",
      to: "expenses",
      hint: "Post operating expenses",
      adminOnly: true,
    },
    {
      label: "Close Period",
      to: "close-period",
      hint: "Post closing entry + lock period",
      adminOnly: true,
    },
  ];

  const visible = links.filter((l) => (l.adminOnly ? isAdmin : true));

  return (
    <div className="bg-white border rounded-xl p-5">
      <h3 className="text-base font-semibold">Quick Links</h3>
      <p className="text-sm text-gray-600 mt-1">
        Jump to common accounting actions and reports.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        {visible.map((l) => (
          <Link
            key={l.to}
            to={l.to}
            className="rounded-xl border p-4 hover:bg-gray-50 transition"
          >
            <div className="font-semibold text-gray-900">{l.label}</div>
            <div className="text-sm text-gray-600 mt-1">{l.hint}</div>
          </Link>
        ))}
      </div>

      {!isAdmin && (
        <p className="text-xs text-gray-500 mt-4">
          Posting actions (Opening Balances, Expenses, Close Period) are admin-only.
        </p>
      )}
    </div>
  );
}
