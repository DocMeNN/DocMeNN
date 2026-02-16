// src/pages/OpeningBalancesPage.jsx

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createOpeningBalances } from "../api/accounting";
import { formatMoney } from "../utils/money";
import AccountCodeInput from "../components/accounting/AccountCodeInput";

function getErrorMessage(err, fallback) {
  return (
    err?.response?.data?.detail ||
    err?.response?.data?.error?.message ||
    err?.message ||
    fallback
  );
}

function todayISO() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function toAmountNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : NaN;
}

export default function OpeningBalancesPage() {
  const queryClient = useQueryClient();

  const [businessId, setBusinessId] = useState("");
  const [asOfDate, setAsOfDate] = useState(todayISO());
  const [lines, setLines] = useState([
    { account_code: "", dc: "D", amount: "" },
    { account_code: "", dc: "C", amount: "" },
  ]);

  const totals = useMemo(() => {
    let debit = 0;
    let credit = 0;

    for (const l of lines) {
      const amt = toAmountNumber(l.amount);
      if (!Number.isFinite(amt) || amt <= 0) continue;
      if (l.dc === "D") debit += amt;
      if (l.dc === "C") credit += amt;
    }

    debit = Math.round(debit * 100) / 100;
    credit = Math.round(credit * 100) / 100;

    return { debit, credit, balanced: debit === credit && debit > 0 };
  }, [lines]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!businessId.trim()) throw new Error("business_id is required.");
      if (!asOfDate || !/^\d{4}-\d{2}-\d{2}$/.test(asOfDate)) {
        throw new Error("as_of_date must be in YYYY-MM-DD format.");
      }

      const payloadLines = lines
        .map((l) => ({
          account_code: String(l.account_code || "").trim(),
          dc: l.dc,
          amount: toAmountNumber(l.amount),
        }))
        .filter((l) => l.account_code && Number.isFinite(l.amount) && l.amount > 0);

      if (payloadLines.length === 0)
        throw new Error("At least one valid line is required.");

      let debit = 0;
      let credit = 0;
      for (const l of payloadLines) {
        if (l.dc === "D") debit += l.amount;
        if (l.dc === "C") credit += l.amount;
      }
      debit = Math.round(debit * 100) / 100;
      credit = Math.round(credit * 100) / 100;

      if (debit !== credit) {
        throw new Error(
          `Opening balances must balance. Debits=${debit.toFixed(
            2
          )} Credits=${credit.toFixed(2)}`
        );
      }

      return createOpeningBalances({
        business_id: businessId.trim(),
        as_of_date: asOfDate,
        lines: payloadLines,
      });
    },
    retry: 0,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounting", "overview-kpis"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "trial-balance"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "profit-and-loss"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "balance-sheet"] }),
      ]);
    },
  });

  function updateLine(idx, patch) {
    setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)));
  }

  function addLine(dc = "D") {
    setLines((prev) => [...prev, { account_code: "", dc, amount: "" }]);
  }

  function removeLine(idx) {
    setLines((prev) => prev.filter((_, i) => i !== idx));
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Opening Balances</h2>
        <p className="text-sm text-gray-600 mt-1">
          Set starting financial position as at a date. Debits must equal credits.
        </p>
      </div>

      <div className="bg-white border rounded-xl p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Business ID">
            <input
              value={businessId}
              onChange={(e) => setBusinessId(e.target.value)}
              className="w-full border rounded-lg px-3 py-2"
              placeholder="e.g. PHARM-001"
            />
          </Field>

          <Field label="As Of Date (YYYY-MM-DD)">
            <input
              value={asOfDate}
              onChange={(e) => setAsOfDate(e.target.value)}
              className="w-full border rounded-lg px-3 py-2"
              placeholder="2026-01-01"
            />
          </Field>

          <div className="rounded-lg border p-4 flex flex-col justify-center">
            <p className="text-sm text-gray-600">Totals</p>
            <p className="text-sm mt-1">
              <span className="text-gray-500">Debits:</span>{" "}
              <span className="font-semibold">{formatMoney(totals.debit)}</span>
              {"  "}•{"  "}
              <span className="text-gray-500">Credits:</span>{" "}
              <span className="font-semibold">{formatMoney(totals.credit)}</span>
            </p>
            <p className="text-sm mt-1">
              Status:{" "}
              {totals.balanced ? (
                <span className="font-semibold text-green-700">Balanced ✅</span>
              ) : (
                <span className="font-semibold text-red-700">Not balanced ❌</span>
              )}
            </p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full border border-gray-200">
            <thead>
              <tr className="bg-gray-50">
                <th className="border p-2 text-left">Account Code</th>
                <th className="border p-2 text-left">D/C</th>
                <th className="border p-2 text-left">Amount</th>
                <th className="border p-2 text-left"></th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line, idx) => (
                <tr key={idx}>
                  <td className="border p-2 min-w-[340px]">
                    <AccountCodeInput
                      compact
                      value={line.account_code}
                      onChange={(v) => updateLine(idx, { account_code: v })}
                      placeholder="e.g. 1000 / 1010 / 1100 / 2000 / 3100"
                      semanticPicks={[
                        { label: "Cash", code: "1000" },
                        { label: "Bank", code: "1010" },
                        { label: "AP", code: "2000" },
                        { label: "Retained", code: "3100" },
                      ]}
                    />
                  </td>
                  <td className="border p-2">
                    <select
                      value={line.dc}
                      onChange={(e) => updateLine(idx, { dc: e.target.value })}
                      className="w-full border rounded-lg px-3 py-2 bg-white"
                    >
                      <option value="D">D (Debit)</option>
                      <option value="C">C (Credit)</option>
                    </select>
                  </td>
                  <td className="border p-2">
                    <input
                      value={line.amount}
                      onChange={(e) => updateLine(idx, { amount: e.target.value })}
                      className="w-full border rounded-lg px-3 py-2"
                      placeholder="0.00"
                      inputMode="decimal"
                    />
                  </td>
                  <td className="border p-2">
                    <button
                      type="button"
                      onClick={() => removeLine(idx)}
                      className="px-3 py-2 rounded-lg border hover:bg-gray-50"
                      disabled={lines.length <= 1}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => addLine("D")}
            className="px-4 py-2 rounded-lg border hover:bg-gray-50"
          >
            + Add Debit Line
          </button>
          <button
            type="button"
            onClick={() => addLine("C")}
            className="px-4 py-2 rounded-lg border hover:bg-gray-50"
          >
            + Add Credit Line
          </button>

          <div className="ml-auto flex gap-3">
            <button
              type="button"
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending || !totals.balanced}
              className="px-4 py-2 rounded-lg bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-60"
            >
              {mutation.isPending ? "Posting…" : "Post Opening Balances"}
            </button>

            <button
              type="button"
              onClick={() => {
                setBusinessId("");
                setAsOfDate(todayISO());
                setLines([
                  { account_code: "", dc: "D", amount: "" },
                  { account_code: "", dc: "C", amount: "" },
                ]);
              }}
              className="px-4 py-2 rounded-lg border hover:bg-gray-50"
            >
              Reset
            </button>
          </div>
        </div>

        {mutation.isError && (
          <div className="rounded-lg border bg-white p-4">
            <p className="text-sm font-medium text-gray-800">
              Couldn’t post opening balances
            </p>
            <p className="text-sm text-gray-600 mt-1">
              {getErrorMessage(mutation.error, "Opening balances failed.")}
            </p>
          </div>
        )}
      </div>

      {mutation.isSuccess && (
        <div className="bg-white border rounded-xl p-5 space-y-2">
          <h3 className="text-base font-semibold">Opening Balance Receipt</h3>

          <div className="rounded-lg border p-4 text-sm text-gray-700 space-y-1">
            <div>
              <span className="text-gray-500">ID:</span>{" "}
              <span className="font-mono">{mutation.data?.id}</span>
            </div>
            <div>
              <span className="text-gray-500">Reference:</span>{" "}
              <span className="font-mono">{mutation.data?.reference}</span>
            </div>
            <div>
              <span className="text-gray-500">Posted At:</span>{" "}
              <span>{String(mutation.data?.posted_at)}</span>
            </div>
            <div>
              <span className="text-gray-500">Description:</span>{" "}
              <span>{mutation.data?.description}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-sm text-gray-600 mb-1">{label}</span>
      {children}
    </label>
  );
}
