// src/pages/ClosePeriodPage.jsx

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { closePeriod } from "../api/accounting";
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

function isISODateOnly(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function todayISO() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function ClosePeriodPage() {
  const queryClient = useQueryClient();

  const [form, setForm] = useState({
    start_date: "",
    end_date: todayISO(),
    retained_earnings_account_code: "",
    confirm: false,
  });

  const canSubmit = useMemo(() => {
    if (!form.confirm) return false;
    if (!isISODateOnly(form.start_date) || !isISODateOnly(form.end_date))
      return false;
    return true;
  }, [form.confirm, form.start_date, form.end_date]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!isISODateOnly(form.start_date)) {
        throw new Error("Start date must be in YYYY-MM-DD format.");
      }
      if (!isISODateOnly(form.end_date)) {
        throw new Error("End date must be in YYYY-MM-DD format.");
      }
      if (!form.confirm) {
        throw new Error("Please confirm before closing the period.");
      }

      const code = String(form.retained_earnings_account_code || "").trim();

      const payload = {
        start_date: form.start_date,
        end_date: form.end_date,
        ...(code ? { retained_earnings_account_code: code } : {}),
      };

      return closePeriod(payload);
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

  const result = mutation.data || null;
  const summary = result?.summary || null;
  const journal = result?.journal_entry || null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Close Period</h2>
        <p className="text-sm text-gray-600 mt-1">
          Posts period totals and rolls net profit into retained earnings.
        </p>
      </div>

      <div className="bg-white border rounded-xl p-5 space-y-4">
        <div>
          <h3 className="text-base font-semibold">Period Range</h3>
          <p className="text-sm text-gray-600 mt-1">
            Enter start and end dates (YYYY-MM-DD).
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Start Date (YYYY-MM-DD)">
            <input
              value={form.start_date}
              onChange={(e) =>
                setForm((p) => ({ ...p, start_date: e.target.value }))
              }
              className="w-full border rounded-lg px-3 py-2"
              placeholder="2026-01-01"
            />
          </Field>

          <Field label="End Date (YYYY-MM-DD)">
            <input
              value={form.end_date}
              onChange={(e) =>
                setForm((p) => ({ ...p, end_date: e.target.value }))
              }
              className="w-full border rounded-lg px-3 py-2"
              placeholder="2026-01-31"
            />
          </Field>

          <div className="md:col-span-1">
            <AccountCodeInput
              label="Retained Earnings A/C (optional override)"
              note="Must be an EQUITY account in the active chart"
              accountTypeFilter="EQUITY"
              value={form.retained_earnings_account_code}
              onChange={(v) =>
                setForm((p) => ({ ...p, retained_earnings_account_code: v }))
              }
              placeholder="Defaults to chart retained earnings"
              semanticPicks={[{ label: "Retained Earnings", code: "3100" }]}
            />
          </div>
        </div>

        <div className="rounded-lg border bg-white p-4">
          <p className="text-sm font-medium text-gray-800">
            Warning: period closing is irreversible
          </p>
          <p className="text-sm text-gray-600 mt-1">
            Closing posts a journal entry and locks the period (prevents double
            closing). Only proceed if dates are correct.
          </p>

          <label className="flex items-center gap-2 mt-3 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.confirm}
              onChange={(e) =>
                setForm((p) => ({ ...p, confirm: e.target.checked }))
              }
            />
            I confirm I want to close this period.
          </label>
        </div>

        {mutation.isError && (
          <div className="rounded-lg border bg-white p-4">
            <p className="text-sm font-medium text-gray-800">
              Couldn’t close period
            </p>
            <p className="text-sm text-gray-600 mt-1">
              {getErrorMessage(mutation.error, "Period close failed.")}
            </p>
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={() => mutation.mutate()}
            disabled={!canSubmit || mutation.isPending}
            className="px-4 py-2 rounded-lg bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-60"
          >
            {mutation.isPending ? "Closing…" : "Close Period"}
          </button>

          <button
            type="button"
            onClick={() =>
              setForm({
                start_date: "",
                end_date: todayISO(),
                retained_earnings_account_code: "",
                confirm: false,
              })
            }
            className="px-4 py-2 rounded-lg border hover:bg-gray-50"
          >
            Reset
          </button>
        </div>
      </div>

      {mutation.isSuccess && (
        <div className="bg-white border rounded-xl p-5 space-y-3">
          <h3 className="text-base font-semibold">Close Period Receipt</h3>

          {summary && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <ReceiptCard
                title="Total Revenue"
                value={formatMoney(Number(summary.total_revenue ?? 0))}
              />
              <ReceiptCard
                title="Total Expenses"
                value={formatMoney(Number(summary.total_expenses ?? 0))}
              />
              <ReceiptCard
                title="Net Profit"
                value={formatMoney(Number(summary.net_profit ?? 0))}
              />
            </div>
          )}

          {journal && (
            <div className="rounded-lg border p-4">
              <p className="text-sm font-medium text-gray-800">
                Journal Entry Posted
              </p>
              <div className="text-sm text-gray-600 mt-2 space-y-1">
                <div>
                  <span className="text-gray-500">ID:</span>{" "}
                  <span className="font-mono">{journal.id}</span>
                </div>
                <div>
                  <span className="text-gray-500">Reference:</span>{" "}
                  <span className="font-mono">{journal.reference}</span>
                </div>
                <div>
                  <span className="text-gray-500">Posted At:</span>{" "}
                  <span>{String(journal.posted_at)}</span>
                </div>
                <div>
                  <span className="text-gray-500">Description:</span>{" "}
                  <span>{journal.description}</span>
                </div>
              </div>
            </div>
          )}
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

function ReceiptCard({ title, value }) {
  return (
    <div className="bg-white border rounded-xl p-5">
      <p className="text-sm text-gray-500">{title}</p>
      <p className="text-xl font-semibold mt-2">{value}</p>
    </div>
  );
}
