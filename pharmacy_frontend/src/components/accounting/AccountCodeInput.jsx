// src/components/accounting/AccountCodeInput.jsx

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAccounts } from "../../api/accounting";

/**
 * AccountCodeInput (v2)
 * - Backend-driven: loads active chart accounts from GET /accounting/accounts/
 * - Safe fallback: COMMON_ACCOUNTS if backend fails / not available
 * - Search: code + name
 * - Optional filter by account_type (EXPENSE, EQUITY, ASSET, LIABILITY, REVENUE)
 * - Keeps semantic quick picks
 */

const COMMON_ACCOUNTS = [
  { code: "1000", name: "Cash", account_type: "ASSET" },
  { code: "1010", name: "Bank", account_type: "ASSET" },
  { code: "1100", name: "Inventory / AR (varies by chart)", account_type: "ASSET" },
  { code: "1200", name: "Inventory / AR (varies by chart)", account_type: "ASSET" },

  { code: "2000", name: "Accounts Payable", account_type: "LIABILITY" },
  { code: "2100", name: "VAT Payable", account_type: "LIABILITY" },

  { code: "3000", name: "Owner Capital / Equity", account_type: "EQUITY" },
  { code: "3100", name: "Retained Earnings", account_type: "EQUITY" },

  { code: "4000", name: "Sales Revenue", account_type: "REVENUE" },
  { code: "4050", name: "Sales Discounts (contra-revenue)", account_type: "REVENUE" },

  { code: "5000", name: "COGS", account_type: "EXPENSE" },
  { code: "5100", name: "Operating Expenses (pharmacy chart)", account_type: "EXPENSE" },
  { code: "6000", name: "Operating Expenses / Rent (retail chart)", account_type: "EXPENSE" },
  { code: "6100", name: "Utilities", account_type: "EXPENSE" },
  { code: "6200", name: "Salaries & Wages", account_type: "EXPENSE" },
];

function normalizeAccount(a) {
  if (!a) return null;

  const code = String(a.code || "").trim();
  if (!code) return null;

  const name = String(a.name || "").trim();
  const account_type = String(a.account_type || "").trim().toUpperCase();

  return {
    id: a.id ?? code,
    code,
    name: name || "—",
    account_type: account_type || "—",
    is_active: a.is_active !== false,
  };
}

function mergeAndDedupByCode(primary = [], fallback = []) {
  const seen = new Set();
  const out = [];

  for (const item of [...primary, ...fallback]) {
    const a = normalizeAccount(item);
    if (!a) continue;
    if (seen.has(a.code)) continue;
    seen.add(a.code);
    out.push(a);
  }

  // sort by code for deterministic UI
  out.sort((x, y) => x.code.localeCompare(y.code));
  return out;
}

function matchesSearch(a, search) {
  if (!search) return true;
  const s = search.toLowerCase();
  return (
    a.code.toLowerCase().includes(s) ||
    (a.name || "").toLowerCase().includes(s) ||
    (a.account_type || "").toLowerCase().includes(s)
  );
}

export default function AccountCodeInput({
  value,
  onChange,
  label,
  placeholder = "e.g. 5100",
  disabled = false,
  semanticPicks = [],
  note,

  /**
   * Optional:
   * accountTypeFilter: "EXPENSE" | "EQUITY" | "ASSET" | "LIABILITY" | "REVENUE"
   * If provided, limits suggestions & search list.
   */
  accountTypeFilter = null,

  /**
   * Optional:
   * If true, hides the search dropdown UI and only keeps datalist suggestions.
   */
  compact = false,
}) {
  const [search, setSearch] = useState("");

  const accountsQuery = useQuery({
    queryKey: ["accounting", "accounts"],
    queryFn: fetchAccounts,
    retry: 1,
    staleTime: 5 * 60 * 1000, // cache accounts for 5 mins
    refetchOnWindowFocus: false,
  });

  const mergedAccounts = useMemo(() => {
    const apiAccounts = Array.isArray(accountsQuery.data)
      ? accountsQuery.data
      : Array.isArray(accountsQuery.data?.results)
      ? accountsQuery.data.results
      : [];

    // Prefer API accounts; fallback to COMMON_ACCOUNTS
    return mergeAndDedupByCode(apiAccounts, COMMON_ACCOUNTS);
  }, [accountsQuery.data]);

  const filteredAccounts = useMemo(() => {
    const type = accountTypeFilter ? String(accountTypeFilter).toUpperCase() : null;

    return mergedAccounts.filter((a) => {
      if (!a.is_active) return false;
      if (type && a.account_type !== type) return false;
      return matchesSearch(a, search);
    });
  }, [mergedAccounts, accountTypeFilter, search]);

  const datalistId = useMemo(() => {
    const type = accountTypeFilter ? String(accountTypeFilter).toLowerCase() : "all";
    // stable-ish id per type (prevents collisions if multiple inputs on one page)
    return `account-code-suggestions-${type}`;
  }, [accountTypeFilter]);

  const statusHint =
    accountsQuery.isLoading
      ? "Loading accounts…"
      : accountsQuery.isError
      ? "Accounts list unavailable (fallback enabled)"
      : "Accounts loaded";

  return (
    <div className="space-y-2">
      {label && (
        <div className="text-sm text-gray-600">
          {label}
          {note ? <span className="text-gray-400"> — {note}</span> : null}
        </div>
      )}

      {/* Input + datalist */}
      <div className="flex flex-wrap gap-2">
        <input
          value={value || ""}
          onChange={(e) => onChange?.(e.target.value)}
          className="w-full border rounded-lg px-3 py-2"
          placeholder={placeholder}
          disabled={disabled}
          list={datalistId}
          inputMode="numeric"
        />

        <datalist id={datalistId}>
          {filteredAccounts.slice(0, 200).map((a) => (
            <option key={a.code} value={a.code}>
              {a.name} ({a.account_type})
            </option>
          ))}
        </datalist>

        {/* Semantic quick picks */}
        {Array.isArray(semanticPicks) && semanticPicks.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {semanticPicks.map((p) => (
              <button
                key={`${p.label}-${p.code}`}
                type="button"
                disabled={disabled}
                onClick={() => onChange?.(p.code)}
                className="px-3 py-2 rounded-lg border hover:bg-gray-50 text-sm"
                title={`Set code to ${p.code}`}
              >
                {p.label}: <span className="font-mono">{p.code}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {!compact && (
        <div className="space-y-2">
          {/* Search box */}
          <div className="flex items-center gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full border rounded-lg px-3 py-2"
              placeholder={
                accountTypeFilter
                  ? `Search ${accountTypeFilter.toLowerCase()} accounts (code or name)…`
                  : "Search accounts (code or name)…"
              }
              disabled={disabled}
            />
          </div>

          {/* Dropdown list */}
          <div className="border rounded-xl bg-white overflow-hidden">
            <div className="px-3 py-2 text-xs text-gray-500 border-b flex items-center justify-between">
              <span>{statusHint}</span>
              <span className="text-gray-400">
                {accountTypeFilter ? `Filter: ${accountTypeFilter}` : "All types"}
              </span>
            </div>

            <div className="max-h-56 overflow-y-auto">
              {filteredAccounts.length === 0 ? (
                <div className="p-3 text-sm text-gray-600">
                  No accounts match your search.
                </div>
              ) : (
                filteredAccounts.slice(0, 100).map((a) => (
                  <button
                    key={a.code}
                    type="button"
                    disabled={disabled}
                    onClick={() => onChange?.(a.code)}
                    className="w-full text-left px-3 py-2 hover:bg-gray-50 border-b last:border-b-0"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm">{a.code}</span>
                      <span className="text-xs text-gray-500">{a.account_type}</span>
                    </div>
                    <div className="text-sm text-gray-800 mt-1">{a.name}</div>
                  </button>
                ))
              )}
            </div>
          </div>

          <p className="text-xs text-gray-500">
            Tip: The list reflects the <span className="font-medium">active chart</span> on the backend.
            If backend is unreachable, suggestions fall back to common codes.
          </p>
        </div>
      )}
    </div>
  );
}
