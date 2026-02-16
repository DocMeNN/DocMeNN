/**
 * ======================================================
 * PATH: src/features/reports/posReports.api.js
 * ======================================================
 *
 * POS REPORTS API (Daily Sales, Cash Recon, Z-Report)
 *
 * Fix:
 * - Your axiosClient already includes the "/api" prefix via baseURL.
 * - The 404 is most likely because the backend route is NOT actually
 *   mounted at "/sales/reports".
 * - To make this resilient (and unblock you fast), we try a small set of
 *   likely base paths and fall back on 404 until we hit the real one.
 *
 * Golden Rule:
 * - You paste → I return a complete copy-replace file. No partial merges.
 * ======================================================
 */

import axiosClient from "../../api/axiosClient";

function toQuery(params = {}) {
  const qp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && String(v).trim() !== "") qp.set(k, v);
  });
  const s = qp.toString();
  return s ? `?${s}` : "";
}

/**
 * We try a few candidate mount points because projects differ:
 * - Some mount these under sales/
 * - Some under accounting/
 * - Some under pos/ or reports/
 *
 * Once we hit the correct one, everything works without changing the UI.
 */
const BASE_CANDIDATES = [
  "/sales/reports",
  "/sales/sales/reports",
  "/pos/reports",
  "/reports/pos",
  "/accounting/pos-reports",
];

function isNotFoundError(err) {
  return err?.response?.status === 404;
}

function isLikelyBadMethodOrAuth(err) {
  const s = err?.response?.status;
  return s === 401 || s === 403 || s === 405;
}

async function getWithBaseFallback(buildPathFn) {
  let lastErr = null;

  for (const base of BASE_CANDIDATES) {
    const url = buildPathFn(base);

    try {
      const res = await axiosClient.get(url);
      return res.data;
    } catch (err) {
      lastErr = err;

      // If it's auth/method, do NOT fallback — the route exists but is blocked/misused.
      if (isLikelyBadMethodOrAuth(err)) throw err;

      // Only fallback on 404 (route not found)
      if (!isNotFoundError(err)) throw err;
    }
  }

  // None matched: throw the last 404 (best signal for debugging)
  throw lastErr || new Error("POS reports endpoint not found (all candidates failed).");
}

/** ---------------------------
 * Reports
 * -------------------------- */

export async function fetchDailySalesReport({ date } = {}) {
  const qs = toQuery({ date });
  return getWithBaseFallback((base) => `${base}/daily/${qs}`);
}

export async function fetchCashReconReport({ date } = {}) {
  const qs = toQuery({ date });
  return getWithBaseFallback((base) => `${base}/cash-recon/${qs}`);
}

export async function fetchZReport({ date } = {}) {
  const qs = toQuery({ date });
  return getWithBaseFallback((base) => `${base}/z-report/${qs}`);
}
