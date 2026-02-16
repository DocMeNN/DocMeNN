// src/pages/AccountingDashboard.jsx

/**
 * ======================================================
 * PATH: src/pages/AccountingDashboard.jsx
 * ======================================================
 * ACCOUNTING DASHBOARD (PRODUCTION LANDING)
 *
 * Goal:
 * - Clean landing page for Accounting (no internal milestone checklist).
 * - Direct links to the real report screens.
 *
 * Notes:
 * - Reports populate automatically once journal entries exist (POS sales/refunds, expenses, opening balances).
 * ======================================================
 */

import { Link } from "react-router-dom";

export default function AccountingDashboard() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold mb-2">Accounting Overview</h1>
        <p className="text-gray-600">
          Financial reports and accounting statements
        </p>
      </div>

      <div className="rounded-lg border bg-white p-4">
        <p className="text-sm text-gray-700 font-medium">Getting started</p>
        <p className="text-sm text-gray-600 mt-1">
          If your reports are showing zero values, it usually means no journal
          entries have been posted yet. Once POS sales/refunds, expenses, or
          opening balances are posted into the ledger, these reports will
          populate automatically.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card
          title="Trial Balance"
          description="Verify debits and credits balance"
          to="/dashboard/admin/accounting/trial-balance"
        />

        <Card
          title="Profit & Loss"
          description="Income, expenses and net profit"
          to="/dashboard/admin/accounting/profit-and-loss"
        />

        <Card
          title="Balance Sheet"
          description="Assets, liabilities and equity"
          to="/dashboard/admin/accounting/balance-sheet"
        />
      </div>

      {/* Optional: add Journals / Ledger drilldown if you have routes */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card
          title="Journal Entries"
          description="See POS_SALE / POS_REFUND / PARTIAL_REFUND postings"
          to="/dashboard/admin/accounting/journals"
        />
        <Card
          title="Opening Balances"
          description="Post opening balances into the ledger (admin)"
          to="/dashboard/admin/accounting/opening-balances"
        />
        <Card
          title="Expenses"
          description="Post expenses into the ledger (admin)"
          to="/dashboard/admin/accounting/expenses"
        />
      </div>
    </div>
  );
}

function Card({ title, description, to }) {
  return (
    <Link
      to={to}
      className="block bg-white rounded-lg shadow p-6 hover:shadow-md transition"
    >
      <h3 className="font-semibold text-lg mb-2">{title}</h3>
      <p className="text-sm text-gray-600">{description}</p>
    </Link>
  );
}
