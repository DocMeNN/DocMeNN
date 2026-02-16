// src/pages/ExpensesPage.jsx

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createExpense, fetchExpenses } from "../api/accounting";
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

function normalizeExpenseRows(data) {
  const raw = Array.isArray(data)
    ? data
    : Array.isArray(data?.results)
    ? data.results
    : [];

  return raw.map((e, idx) => ({
    _key: e?.id ?? `${idx}`,
    id: e?.id ?? "—",
    expenseDate: e?.expense_date || e?.date || e?.created_at || "—",
    vendor: e?.vendor || "—",
    narration: e?.narration || e?.description || e?.memo || "—",
    paymentMethod: e?.payment_method || e?.payment || "—",
    amount: e?.amount ?? "—",
    expenseAccount:
      e?.expense_account?.code ||
      e?.expense_account_code ||
      e?.expense_account ||
      "—",
    paymentAccount:
      e?.payment_account?.code ||
      e?.payment_account_code ||
      e?.payment_account ||
      "—",
    journalRef: e?.posted_journal_entry?.id || e?.posted_journal_entry || "—",
  }));
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

export default function ExpensesPage() {
  const queryClient = useQueryClient();

  const [form, setForm] = useState({
    expense_date: todayISO(),
    amount: "",
    expense_account_code: "",
    payment_method: "cash",
    payable_account_code: "",
    vendor: "",
    narration: "",
  });

  const isCredit = form.payment_method === "credit";

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["accounting", "expenses"],
    queryFn: () => fetchExpenses(),
    retry: 1,
    refetchOnWindowFocus: false,
  });

  const rows = useMemo(() => normalizeExpenseRows(data), [data]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (!isISODateOnly(form.expense_date)) {
        throw new Error("Expense date must be in YYYY-MM-DD format.");
      }

      const amountNum = Number(form.amount);
      if (!Number.isFinite(amountNum) || amountNum <= 0) {
        throw new Error("Amount must be a positive number.");
      }

      if (!form.expense_account_code?.trim()) {
        throw new Error("Expense account code is required.");
      }

      const method = String(form.payment_method || "").trim().toLowerCase();
      if (!["cash", "bank", "credit"].includes(method)) {
        throw new Error("Payment method must be cash, bank, or credit.");
      }

      // Backend allows payable override to be omitted/blank even for credit.
      const payable = String(form.payable_account_code || "").trim();

      const payload = {
        expense_date: form.expense_date,
        amount: amountNum,
        expense_account_code: form.expense_account_code.trim(),
        payment_method: method,
        ...(method === "credit" && payable ? { payable_account_code: payable } : {}),
        ...(form.vendor.trim() ? { vendor: form.vendor.trim() } : {}),
        ...(form.narration.trim() ? { narration: form.narration.trim() } : {}),
      };

      return createExpense(payload);
    },
    retry: 0,
    onSuccess: async () => {
      setForm((prev) => ({
        ...prev,
        amount: "",
        vendor: "",
        narration: "",
        payable_account_code: "",
      }));

      await Promise.all([
        // Accounting pages
        queryClient.invalidateQueries({ queryKey: ["accounting", "expenses"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "overview-kpis"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "trial-balance"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "profit-and-loss"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "balance-sheet"] }),

        // ✅ Admin KPI dashboard caches (so Admin cards update immediately)
        queryClient.invalidateQueries({ queryKey: ["admin", "kpis", "expenses"] }),
        queryClient.invalidateQueries({ queryKey: ["admin", "kpis", "accounting-overview"] }),
      ]);
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Expenses</h2>
        <p className="text-sm text-gray-600 mt-1">
          Create and post expenses to the ledger (atomic, audit-safe).
        </p>
      </div>

      <div className="bg-white border rounded-xl p-5 space-y-4">
        <div>
          <h3 className="text-base font-semibold">Post Expense</h3>
          <p className="text-sm text-gray-600 mt-1">
            Backend posts the journal entry. Frontend only collects inputs.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Expense Date (YYYY-MM-DD)">
            <input
              value={form.expense_date}
              onChange={(e) =>
                setForm((p) => ({ ...p, expense_date: e.target.value }))
              }
              className="w-full border rounded-lg px-3 py-2"
              placeholder="2026-01-25"
            />
          </Field>

          <Field label="Amount">
            <input
              value={form.amount}
              onChange={(e) => setForm((p) => ({ ...p, amount: e.target.value }))}
              className="w-full border rounded-lg px-3 py-2"
              placeholder="1000"
              inputMode="decimal"
            />
          </Field>

          <Field label="Payment Method">
            <select
              value={form.payment_method}
              onChange={(e) =>
                setForm((p) => ({ ...p, payment_method: e.target.value }))
              }
              className="w-full border rounded-lg px-3 py-2 bg-white"
            >
              <option value="cash">cash</option>
              <option value="bank">bank</option>
              <option value="credit">credit</option>
            </select>
          </Field>

          <div className="md:col-span-2">
            <AccountCodeInput
              label="Expense Account Code"
              note="Must be an EXPENSE account in the active chart"
              accountTypeFilter="EXPENSE"
              value={form.expense_account_code}
              onChange={(v) => setForm((p) => ({ ...p, expense_account_code: v }))}
              placeholder="e.g. 5100 / 6000"
              semanticPicks={[
                { label: "Operating Exp", code: "5100" },
                { label: "Operating Exp", code: "6000" },
                { label: "COGS", code: "5000" },
              ]}
            />
          </div>

          {isCredit && (
            <div className="md:col-span-1">
              <AccountCodeInput
                label="Payable A/C Code (optional override)"
                note="Credit mode: should be a LIABILITY account (defaults to Accounts Payable)"
                accountTypeFilter="LIABILITY"
                value={form.payable_account_code}
                onChange={(v) => setForm((p) => ({ ...p, payable_account_code: v }))}
                placeholder="defaults to Accounts Payable"
                semanticPicks={[{ label: "AP", code: "2000" }]}
              />
            </div>
          )}

          <Field label="Vendor (optional)">
            <input
              value={form.vendor}
              onChange={(e) => setForm((p) => ({ ...p, vendor: e.target.value }))}
              className="w-full border rounded-lg px-3 py-2"
              placeholder="e.g. Ikeja Electricity"
            />
          </Field>

          <div className="md:col-span-3">
            <Field label="Narration (optional)">
              <input
                value={form.narration}
                onChange={(e) =>
                  setForm((p) => ({ ...p, narration: e.target.value }))
                }
                className="w-full border rounded-lg px-3 py-2"
                placeholder="e.g. Generator fuel for weekend shift"
              />
            </Field>
          </div>
        </div>

        {mutation.isError && (
          <div className="rounded-lg border bg-white p-4">
            <p className="text-sm font-medium text-gray-800">
              Couldn’t post expense
            </p>
            <p className="text-sm text-gray-600 mt-1">
              {getErrorMessage(mutation.error, "Expense posting failed.")}
            </p>
          </div>
        )}

        {mutation.isSuccess && (
          <div className="rounded-lg border bg-white p-4">
            <p className="text-sm font-medium text-gray-800">Expense posted</p>
            <p className="text-sm text-gray-600 mt-1">Ledger updated.</p>
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="px-4 py-2 rounded-lg bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-60"
          >
            {mutation.isPending ? "Posting…" : "Post Expense"}
          </button>

          <button
            type="button"
            onClick={() =>
              setForm({
                expense_date: todayISO(),
                amount: "",
                expense_account_code: "",
                payment_method: "cash",
                payable_account_code: "",
                vendor: "",
                narration: "",
              })
            }
            className="px-4 py-2 rounded-lg border hover:bg-gray-50"
          >
            Reset
          </button>

          <div className="ml-auto text-sm text-gray-600 flex items-center">
            {form.amount && Number(form.amount) > 0 ? (
              <span>Preview: {formatMoney(Number(form.amount))}</span>
            ) : (
              <span className="text-gray-400">Preview: —</span>
            )}
          </div>
        </div>
      </div>

      <div className="bg-white border rounded-xl p-5">
        <h3 className="text-base font-semibold mb-3">Expense History</h3>

        {isLoading && <div className="text-gray-600">Loading expenses…</div>}

        {isError && (
          <div className="rounded-lg border bg-white p-4">
            <p className="text-sm font-medium text-gray-800">
              Couldn’t load expenses
            </p>
            <p className="text-sm text-gray-600 mt-1">
              {getErrorMessage(error, "Failed to load expenses.")}
            </p>
          </div>
        )}

        {!isLoading && !isError && rows.length === 0 && (
          <div className="text-gray-600">No expenses yet.</div>
        )}

        {!isLoading && !isError && rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full border border-gray-200">
              <thead>
                <tr className="bg-gray-50">
                  <th className="border p-2 text-left">Date</th>
                  <th className="border p-2 text-left">Vendor</th>
                  <th className="border p-2 text-left">Narration</th>
                  <th className="border p-2 text-left">Expense A/C</th>
                  <th className="border p-2 text-left">Payment A/C</th>
                  <th className="border p-2 text-left">Method</th>
                  <th className="border p-2 text-left">Amount</th>
                  <th className="border p-2 text-left">Journal</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r._key}>
                    <td className="border p-2">{r.expenseDate}</td>
                    <td className="border p-2">{r.vendor}</td>
                    <td className="border p-2">{r.narration}</td>
                    <td className="border p-2">{r.expenseAccount}</td>
                    <td className="border p-2">{r.paymentAccount}</td>
                    <td className="border p-2">{r.paymentMethod}</td>
                    <td className="border p-2">{String(r.amount)}</td>
                    <td className="border p-2">{r.journalRef}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
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
