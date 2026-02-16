// src/components/accounting/AccountingSummaryCards.jsx

import { formatMoney } from "../../utils/money";

/**
 * Normalize summary payloads so the UI works with:
 * - placeholder/camelCase shape (assets, liabilitiesPlusEquity, netProfit)
 * - backend/contract shape (assets, liabilities, equity, revenue, expenses, net_profit)
 *
 * We prefer *_minor integers when present (exact), but we output major-unit numbers
 * because formatMoney() expects major units.
 */

function toFiniteNumberOrNull(v) {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function minorToMajorOrNull(vMinor) {
  const n = toFiniteNumberOrNull(vMinor);
  if (n === null) return null;
  return n / 100;
}

function normalizeSummary(summary) {
  if (!summary) return null;

  // Detect backend overview shape
  const hasBackendShape =
    summary.assets !== undefined &&
    summary.liabilities !== undefined &&
    summary.equity !== undefined;

  if (hasBackendShape) {
    // Prefer minor units if present (exact integers)
    const assets =
      summary.assets_minor !== undefined
        ? minorToMajorOrNull(summary.assets_minor)
        : toFiniteNumberOrNull(summary.assets);

    const liabilities =
      summary.liabilities_minor !== undefined
        ? minorToMajorOrNull(summary.liabilities_minor)
        : toFiniteNumberOrNull(summary.liabilities);

    const equity =
      summary.equity_minor !== undefined
        ? minorToMajorOrNull(summary.equity_minor)
        : toFiniteNumberOrNull(summary.equity);

    const revenue =
      summary.revenue_minor !== undefined
        ? minorToMajorOrNull(summary.revenue_minor)
        : toFiniteNumberOrNull(summary.revenue ?? summary.income ?? 0);

    const expenses =
      summary.expenses_minor !== undefined
        ? minorToMajorOrNull(summary.expenses_minor)
        : toFiniteNumberOrNull(summary.expenses ?? 0);

    const netProfit =
      summary.net_profit_minor !== undefined
        ? minorToMajorOrNull(summary.net_profit_minor)
        : toFiniteNumberOrNull(summary.net_profit ?? summary.netProfit ?? 0);

    const liabilitiesPlusEquity =
      liabilities === null || equity === null ? null : liabilities + equity;

    return {
      assets,
      liabilitiesPlusEquity,
      revenue,
      expenses,
      netProfit,
    };
  }

  // Fallback to existing UI placeholder shape
  const assets = toFiniteNumberOrNull(summary.assets);
  const liabilitiesPlusEquity = toFiniteNumberOrNull(
    summary.liabilitiesPlusEquity
  );
  const revenue = toFiniteNumberOrNull(summary.revenue);
  const expenses = toFiniteNumberOrNull(summary.expenses);
  const netProfit = toFiniteNumberOrNull(summary.netProfit);

  return {
    assets,
    liabilitiesPlusEquity,
    revenue,
    expenses,
    netProfit,
  };
}

function isAllZeroSummary(summary) {
  if (!summary) return false;

  const normalized = normalizeSummary(summary);
  if (!normalized) return false;

  const values = [
    normalized.assets,
    normalized.liabilitiesPlusEquity,
    normalized.revenue,
    normalized.expenses,
    normalized.netProfit,
  ];

  // If any value is null (unknown), we don't call it "all zero"
  if (values.some((v) => v === null)) return false;

  return values.every((v) => Number.isFinite(v) && v === 0);
}

export default function AccountingSummaryCards({ summary }) {
  if (!summary) return null;

  const normalized = normalizeSummary(summary);
  if (!normalized) return null;

  const showEmptyHint = isAllZeroSummary(summary);

  const cards = [
    { label: "Total Assets", value: normalized.assets },
    { label: "Liabilities + Equity", value: normalized.liabilitiesPlusEquity },
    { label: "Revenue", value: normalized.revenue },
    { label: "Expenses", value: normalized.expenses },
    { label: "Net Profit", value: normalized.netProfit },
  ];

  return (
    <div className="space-y-4">
      {showEmptyHint && (
        <div className="rounded-lg border bg-white p-4">
          <p className="text-sm font-medium text-gray-800">
            No ledger activity yet
          </p>
          <p className="text-sm text-gray-600 mt-1">
            These KPIs will update automatically once transactions are posted to
            the ledger (sales, expenses, opening balances).
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {cards.map((card) => (
          <div
            key={card.label}
            className="bg-white border rounded-xl p-6 shadow-sm"
          >
            <p className="text-sm text-gray-500">{card.label}</p>
            <p className="text-2xl font-semibold mt-2">
              {card.value === null ? "—" : formatMoney(card.value)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
