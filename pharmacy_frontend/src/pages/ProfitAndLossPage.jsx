// src/pages/ProfitAndLossPage.jsx

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchProfitAndLoss } from "../api/accounting";

import ProfitAndLossHeader from "../components/accounting/ProfitAndLossHeader";
import ProfitAndLossTable from "../components/accounting/ProfitAndLossTable";
import ReportDateFilter from "../components/accounting/ReportDateFilter";

function getErrorMessage(err, fallback) {
  return (
    err?.response?.data?.detail ||
    err?.response?.data?.error?.message ||
    err?.message ||
    fallback
  );
}

function isZeroPL(data) {
  if (!data) return false;

  const income = Number(data.income ?? data.revenue ?? 0);
  const expenses = Number(data.expenses ?? 0);
  const net = Number(data.net_profit ?? 0);

  return (
    Number.isFinite(income) &&
    Number.isFinite(expenses) &&
    Number.isFinite(net) &&
    income === 0 &&
    expenses === 0 &&
    net === 0
  );
}

function getMonthRangeISO() {
  // YYYY-MM-DD strings
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);

  const toISODate = (d) => {
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  };

  return { startDate: toISODate(start), endDate: toISODate(end) };
}

export default function ProfitAndLossPage() {
  // Default to current month so user immediately sees something deterministic
  const [filters, setFilters] = useState(() => getMonthRangeISO());

  // We pass date-only values; the API layer converts to ISO datetime boundaries.
  const params = useMemo(() => {
    const start = (filters.startDate || "").trim();
    const end = (filters.endDate || "").trim();

    // If both empty, backend decides defaults (but our UI defaults to month anyway)
    if (!start && !end) return {};

    return {
      ...(start ? { start } : {}),
      ...(end ? { end } : {}),
    };
  }, [filters.startDate, filters.endDate]);

  const { data, isLoading, isError, error, isFetching } = useQuery({
    queryKey: ["accounting", "profit-and-loss", params],
    queryFn: () => fetchProfitAndLoss(params),
    retry: 1,
    refetchOnWindowFocus: false,
  });

  const clearFilters = () => setFilters({ startDate: "", endDate: "" });
  const setThisMonth = () => setFilters(getMonthRangeISO());

  if (isLoading) return <div>Loading Profit &amp; Loss…</div>;

  if (isError) {
    const message = getErrorMessage(error, "Failed to load Profit & Loss.");
    return (
      <div className="rounded-lg border bg-white p-4">
        <p className="text-sm font-medium text-gray-800">
          Couldn’t load Profit &amp; Loss
        </p>
        <p className="text-sm text-gray-600 mt-1">{message}</p>
      </div>
    );
  }

  if (!data) return <div className="text-gray-500">No P&amp;L data.</div>;

  const showEmptyHint = isZeroPL(data);

  const income = data?.income ?? data?.revenue ?? 0;
  const expenses = data?.expenses ?? 0;
  const netProfit = data?.net_profit ?? 0;

  const period = data?.period ?? null;

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-end justify-between gap-3">
        <div className="flex-1">
          <ReportDateFilter
            startDate={filters.startDate}
            endDate={filters.endDate}
            onChange={({ startDate, endDate }) =>
              setFilters({
                startDate: startDate || "",
                endDate: endDate || "",
              })
            }
          />
        </div>

        <div className="flex gap-2 pb-4">
          <button
            type="button"
            onClick={setThisMonth}
            className="px-3 py-2 rounded-md border bg-white hover:bg-gray-50 text-sm"
            title="Set range to this month"
          >
            This Month
          </button>
          <button
            type="button"
            onClick={clearFilters}
            className="px-3 py-2 rounded-md border bg-white hover:bg-gray-50 text-sm"
            title="Clear date filters"
          >
            Clear
          </button>
        </div>
      </div>

      {isFetching && (
        <div className="text-xs text-gray-500 -mt-2">Refreshing…</div>
      )}

      <ProfitAndLossHeader period={period} netProfit={netProfit} />

      {showEmptyHint && (
        <div className="rounded-lg border bg-white p-4">
          <p className="text-sm font-medium text-gray-800">
            No income or expenses recorded in this period
          </p>
          <p className="text-sm text-gray-600 mt-1">
            This is normal if you have not posted sales/expenses yet, or if your
            selected period has no activity.
          </p>
        </div>
      )}

      <ProfitAndLossTable
        income={income}
        expenses={expenses}
        netProfit={netProfit}
      />
    </div>
  );
}
