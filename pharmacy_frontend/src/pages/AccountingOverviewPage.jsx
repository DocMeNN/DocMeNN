// src/pages/AccountingOverviewPage.jsx

/**
 * ======================================================
 * PATH: src/pages/AccountingOverviewPage.jsx
 * ======================================================
 * ACCOUNTING OVERVIEW (UI + API)
 *
 * Cleaned up per screenshot:
 * - Removes internal MilestoneTracker checklist UI.
 * - Presents a real Accounting landing page:
 *   1) KPI Summary Cards (API-backed)
 *   2) Reports (Quick Links)
 *   3) Admin Actions (Opening Balances, Expenses, Close Period, POS Reports)
 *   4) Short user-facing note
 *
 * Golden Rule:
 * - You paste → I return a complete copy-replace file. No partial merges.
 * ======================================================
 */

import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { fetchAccountingOverviewKPIs } from "../api/accounting";
import { useAuth } from "../context/AuthContext";

import AccountingSummaryCards from "../components/accounting/AccountingSummaryCards";
import AccountingQuickLinks from "../components/accounting/AccountingQuickLinks";

function getErrorMessage(err, fallback) {
  return (
    err?.response?.data?.detail ||
    err?.response?.data?.error?.message ||
    err?.message ||
    fallback
  );
}

function SectionCard({ title, children }) {
  return (
    <div className="bg-white border rounded-xl p-5">
      <div className="text-sm font-semibold text-gray-900">{title}</div>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function ActionTile({ title, description, to, disabled, badge }) {
  if (disabled) {
    return (
      <div
        className="block bg-white rounded-lg border p-5 opacity-60 cursor-not-allowed"
        title="Admin only"
      >
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-semibold text-base text-gray-900">{title}</h3>
          {badge ? (
            <span className="text-[11px] px-2 py-1 rounded border bg-gray-50 text-gray-700 border-gray-200">
              {badge}
            </span>
          ) : null}
        </div>
        <p className="text-sm text-gray-600 mt-1">{description}</p>
        <div className="text-xs text-gray-500 mt-3">Restricted</div>
      </div>
    );
  }

  return (
    <Link
      to={to}
      className="block bg-white rounded-lg border p-5 hover:shadow-sm hover:border-gray-300 transition"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold text-base text-gray-900">{title}</h3>
        {badge ? (
          <span className="text-[11px] px-2 py-1 rounded border bg-gray-50 text-gray-700 border-gray-200">
            {badge}
          </span>
        ) : null}
      </div>
      <p className="text-sm text-gray-600 mt-1">{description}</p>
      <div className="text-xs text-blue-600 mt-3">Open</div>
    </Link>
  );
}

export default function AccountingOverviewPage() {
  const { user } = useAuth();
  const isAdmin = String(user?.role || "").toLowerCase() === "admin";

  const {
    data: summary,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["accounting", "overview-kpis"],
    queryFn: () => fetchAccountingOverviewKPIs(),
    retry: 1,
    refetchOnWindowFocus: false,
  });

  if (isLoading) {
    return <div className="text-gray-500">Loading overview…</div>;
  }

  if (isError) {
    const message = getErrorMessage(error, "Failed to load accounting overview.");
    return (
      <div className="rounded-lg border bg-white p-4">
        <p className="text-sm font-medium text-gray-800">
          Couldn’t load Accounting Overview
        </p>
        <p className="text-sm text-gray-600 mt-1">{message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* API-backed KPI summary */}
      <AccountingSummaryCards summary={summary || null} />

      {/* Reports / navigation */}
      <SectionCard title="Reports">
        <div className="text-sm text-gray-600 mb-4">
          Read-only financial statements computed from the authoritative ledger.
        </div>
        <AccountingQuickLinks />
      </SectionCard>

      {/* Admin posting actions */}
      <SectionCard title="Posting Actions (Admin-only)">
        <div className="text-sm text-gray-600">
          These create new immutable journal + ledger postings. Only Admin can post.
        </div>

        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          <ActionTile
            title="Opening Balances"
            description="Post beginning balances (e.g., Cash, Inventory, Equity)."
            to="/accounting/opening-balances"
            disabled={!isAdmin}
            badge="Admin"
          />
          <ActionTile
            title="Expense Posting"
            description="Post expenses into the ledger (rent, utilities, salaries…)."
            to="/accounting/expenses"
            disabled={!isAdmin}
            badge="Admin"
          />
          <ActionTile
            title="Close Period"
            description="Close a period (lock postings, roll profit into retained earnings)."
            to="/accounting/close-period"
            disabled={!isAdmin}
            badge="Admin"
          />
          <ActionTile
            title="POS Reports"
            description="Admin-only operational reports (sales / cashier / store)."
            to="/accounting/pos-reports"
            disabled={!isAdmin}
            badge="Admin"
          />
        </div>
      </SectionCard>

      {/* User-facing helper note */}
      <div className="rounded-lg border bg-white p-4">
        <p className="text-sm font-medium text-gray-800">Note</p>
        <p className="text-sm text-gray-600 mt-1">
          Reports populate automatically once ledger postings exist. POS sales and
          refunds (including partial refunds) post to the journal and ledger. If a
          report looks empty, confirm you have recent JournalEntry records and that
          the report date filters include those posted_at timestamps.
        </p>
      </div>
    </div>
  );
}
