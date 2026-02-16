// src/pages/TrialBalancePage.jsx

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchTrialBalance } from "../api/accounting";
import TrialBalanceTable from "../components/accounting/TrialBalanceTable";
import TrialBalanceHeader from "../components/accounting/TrialBalanceHeader";
import ReportDateFilter from "../components/accounting/ReportDateFilter";

function getErrorMessage(err, fallback) {
  return (
    err?.response?.data?.detail ||
    err?.response?.data?.error?.message ||
    err?.message ||
    fallback
  );
}

// Backend expects as_of=<ISO datetime>. We collect date and convert to end-of-day.
function toAsOfDateTime(dateOnly) {
  if (!dateOnly) return undefined;
  return `${dateOnly}T23:59:59`;
}

export default function TrialBalancePage() {
  const [asOfDate, setAsOfDate] = useState("");

  const params = useMemo(() => {
    const as_of = toAsOfDateTime(asOfDate);
    return as_of ? { as_of } : {};
  }, [asOfDate]);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["accounting", "trial-balance", params],
    queryFn: () => fetchTrialBalance(params),
    retry: 1,
    refetchOnWindowFocus: false,
  });

  if (isLoading) return <div>Loading trial balance…</div>;

  if (isError) {
    const message = getErrorMessage(error, "Failed to load trial balance.");
    return (
      <div className="rounded-lg border bg-white p-4">
        <p className="text-sm font-medium text-gray-800">
          Couldn’t load trial balance
        </p>
        <p className="text-sm text-gray-600 mt-1">{message}</p>
      </div>
    );
  }

  if (!data) return <div className="text-gray-500">No trial balance data.</div>;

  const totals = data?.totals ?? { debit: 0, credit: 0, balanced: true };
  const accounts = Array.isArray(data?.accounts) ? data.accounts : [];

  return (
    <div className="space-y-4">
      <ReportDateFilter
        mode="asOfDateTime"
        asOfDate={asOfDate}
        onChange={({ asOfDate: next }) => setAsOfDate(next || "")}
      />

      <TrialBalanceHeader asOf={data.as_of} balanced={!!totals.balanced} />
      <TrialBalanceTable accounts={accounts} totals={totals} />
    </div>
  );
}
