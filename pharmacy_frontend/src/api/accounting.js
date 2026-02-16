// src/api/accounting.js

import axiosClient from "./axiosClient";

/**
 * ======================================================
 * ACCOUNTING API — LEDGER-DRIVEN FINANCIAL TRUTH
 * ======================================================
 *
 * BACKEND ROUTES:
 * - Accounts (Chart):    GET  /accounting/accounts/
 * - Trial Balance:       GET  /accounting/trial-balance/?as_of=<ISO datetime>
 * - Profit & Loss:       GET  /accounting/profit-and-loss/?start_date=<ISO datetime>&end_date=<ISO datetime>
 * - Balance Sheet:       GET  /accounting/balance-sheet/?as_of_date=<YYYY-MM-DD>
 * - Overview KPIs:       GET  /accounting/overview/?as_of_date=<YYYY-MM-DD>&chart_id=<int>
 * - Opening Balances:    POST /accounting/opening-balances/
 * - Expenses:            GET  /accounting/expenses/   | POST /accounting/expenses/
 * - Close Period:        POST /accounting/close-period/
 *
 * IMPORTANT CONTRACT NOTES:
 * - Backend is authoritative for money + ledger math.
 * - Frontend sends date filters; backend computes.
 * - P&L + Trial Balance require ISO datetime (not date-only).
 */

/** ---------- Normalization Helpers ---------- */

function isPlainObject(value) {
  return (
    value !== null &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    !(value instanceof Date)
  );
}

function isNumericLikeString(value) {
  if (typeof value !== "string") return false;
  const s = value.trim();
  if (!s) return false;
  return /^-?\d+(\.\d+)?$/.test(s);
}

function toNumberStrict(value) {
  if (value === null) return null;
  if (typeof value === "number") return value;

  if (isNumericLikeString(value)) {
    const n = Number(value);
    return Number.isFinite(n) ? n : value;
  }

  return value;
}

function normalizeNumbersDeep(data) {
  if (Array.isArray(data)) return data.map(normalizeNumbersDeep);

  if (isPlainObject(data)) {
    const out = {};
    for (const [key, val] of Object.entries(data)) {
      out[key] = normalizeNumbersDeep(val);
    }
    return out;
  }

  return toNumberStrict(data);
}

function warnOnNumericStringsDeep(data, path = "") {
  if (data === null || data === undefined) return;

  if (Array.isArray(data)) {
    data.forEach((item, idx) =>
      warnOnNumericStringsDeep(item, `${path}[${idx}]`)
    );
    return;
  }

  if (isPlainObject(data)) {
    for (const [key, val] of Object.entries(data)) {
      const nextPath = path ? `${path}.${key}` : key;

      if (isNumericLikeString(val)) {
        // eslint-disable-next-line no-console
        console.warn(
          `[Accounting Contract] Numeric string detected at "${nextPath}":`,
          val
        );
      }

      warnOnNumericStringsDeep(val, nextPath);
    }
  }
}

/** ---------- Param Hygiene ---------- */

function stripEmptyParams(params = {}) {
  const out = {};
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === null) continue;
    if (typeof v === "string" && v.trim() === "") continue;
    out[k] = v;
  }
  return out;
}

function mapParams(params = {}, mapping = {}) {
  const out = { ...(params || {}) };
  for (const [from, to] of Object.entries(mapping)) {
    if (out[from] !== undefined && out[to] === undefined) {
      out[to] = out[from];
      delete out[from];
    }
  }
  return out;
}

/**
 * If a value is "YYYY-MM-DD", convert to ISO datetime.
 * Backend uses parse_datetime for P&L + Trial Balance.
 */
function isISODateOnly(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function toIsoDateTime(value, boundary = "start") {
  if (!value) return value;

  // Already looks like datetime? leave it.
  if (typeof value === "string" && value.includes("T")) return value;

  if (isISODateOnly(value)) {
    return boundary === "end" ? `${value}T23:59:59` : `${value}T00:00:00`;
  }

  return value;
}

async function getNormalized(url, params = {}) {
  const cleaned = stripEmptyParams(params);
  const response = await axiosClient.get(url, { params: cleaned });

  if (import.meta?.env?.DEV) {
    warnOnNumericStringsDeep(response.data);
  }

  return normalizeNumbersDeep(response.data);
}

async function postNormalized(url, payload = {}) {
  const response = await axiosClient.post(url, payload);

  if (import.meta?.env?.DEV) {
    warnOnNumericStringsDeep(response.data);
  }

  return normalizeNumbersDeep(response.data);
}

/** ---------- Master Data (Read-only) ---------- */

export async function fetchAccounts(params = {}) {
  // Active chart accounts for dropdowns + validations
  return getNormalized("/accounting/accounts/", params);
}

/** ---------- Reports (Read-only) ---------- */

export async function fetchTrialBalance(params = {}) {
  // Accept: asOf (date or datetime) OR as_of
  let p = mapParams(params, { asOf: "as_of" });

  // If UI passes date-only, convert to end-of-day snapshot.
  if (p.as_of) p.as_of = toIsoDateTime(p.as_of, "end");

  return getNormalized("/accounting/trial-balance/", p);
}

export async function fetchProfitAndLoss(params = {}) {
  // Accept: start/end (date or datetime) OR start_date/end_date
  let p = mapParams(params, { start: "start_date", end: "end_date" });

  if (p.start_date) p.start_date = toIsoDateTime(p.start_date, "start");
  if (p.end_date) p.end_date = toIsoDateTime(p.end_date, "end");

  return getNormalized("/accounting/profit-and-loss/", p);
}

export async function fetchBalanceSheet(params = {}) {
  // Balance Sheet endpoint expects date-only: as_of_date=YYYY-MM-DD
  const p = mapParams(params, { asOfDate: "as_of_date", as_of: "as_of_date" });
  return getNormalized("/accounting/balance-sheet/", p);
}

export async function fetchAccountingOverviewKPIs(params = {}) {
  // Overview supports: chart_id, as_of_date (date-only).
  // DO NOT send start_date/end_date here (backend doesn't accept them in this endpoint).
  const p = mapParams(params, { asOfDate: "as_of_date" });

  // Defensive: if caller passed start/end, drop them.
  delete p.start;
  delete p.end;
  delete p.start_date;
  delete p.end_date;

  return getNormalized("/accounting/overview/", p);
}

/** ---------- Operations (Posting) ---------- */

export async function fetchExpenses(params = {}) {
  return getNormalized("/accounting/expenses/", params);
}

export async function createExpense(payload) {
  return postNormalized("/accounting/expenses/", payload);
}

export async function closePeriod(payload) {
  return postNormalized("/accounting/close-period/", payload);
}

export async function createOpeningBalances(payload) {
  return postNormalized("/accounting/opening-balances/", payload);
}
