// src/pages/BalanceSheetPage.jsx

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchBalanceSheet } from "../api/accounting";
import { formatMoney } from "../utils/money";
import ReportDateFilter from "../components/accounting/ReportDateFilter";

function getErrorMessage(err, fallback) {
  return (
    err?.response?.data?.detail ||
    err?.response?.data?.error?.message ||
    err?.message ||
    fallback
  );
}

function isZeroBalanceSheet(data) {
  if (!data?.totals) return false;

  const assets = Number(data.totals.assets);
  const liabilities = Number(data.totals.liabilities);
  const equity = Number(data.totals.equity);

  return (
    Number.isFinite(assets) &&
    Number.isFinite(liabilities) &&
    Number.isFinite(equity) &&
    assets === 0 &&
    liabilities === 0 &&
    equity === 0
  );
}

export default function BalanceSheetPage() {
  const [asOfDate, setAsOfDate] = useState("");

  const params = useMemo(() => {
    // backend expects YYYY-MM-DD as_of_date
    return asOfDate ? { as_of_date: asOfDate } : {};
  }, [asOfDate]);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["accounting", "balance-sheet", params],
    queryFn: () => fetchBalanceSheet(params),
    retry: 1,
    refetchOnWindowFocus: false,
  });

  if (isLoading) return <div>Loading Balance Sheet…</div>;

  if (isError) {
    const message = getErrorMessage(error, "Failed to load Balance Sheet.");
    return (
      <div className="rounded-lg border bg-white p-4">
        <p className="text-sm font-medium text-gray-800">
          Couldn’t load Balance Sheet
        </p>
        <p className="text-sm text-gray-600 mt-1">{message}</p>
      </div>
    );
  }

  if (!data) return <div className="text-gray-500">No Balance Sheet data.</div>;

  const showEmptyHint = isZeroBalanceSheet(data);

  return (
    <div className="max-w-4xl space-y-4">
      <ReportDateFilter
        mode="asOf"
        asOfDate={asOfDate}
        onChange={({ asOfDate: next }) => setAsOfDate(next || "")}
      />

      <div>
        <h2 className="text-2xl font-semibold">Balance Sheet</h2>
        <p className="text-sm text-gray-600 mt-1">
          Snapshot of assets, liabilities, and equity at a point in time.
        </p>
      </div>

      {showEmptyHint && (
        <div className="rounded-lg border bg-white p-4">
          <p className="text-sm font-medium text-gray-800">
            No balances recorded yet
          </p>
          <p className="text-sm text-gray-600 mt-1">
            This usually means no opening balances or transactions have been
            posted to the ledger yet. Once posting starts, the Balance Sheet
            will populate automatically.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card title="Assets" value={data.totals.assets} />
        <Card title="Liabilities" value={data.totals.liabilities} />
        <Card title="Equity" value={data.totals.equity} />
      </div>
    </div>
  );
}

function Card({ title, value }) {
  return (
    <div className="bg-white border rounded p-6">
      <h3 className="text-sm text-gray-500 mb-2">{title}</h3>
      <div className="text-xl font-semibold">{formatMoney(value)}</div>
    </div>
  );
}
