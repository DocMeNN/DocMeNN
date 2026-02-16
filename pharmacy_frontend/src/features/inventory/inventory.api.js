/**
 * ======================================================
 * PATH: src/features/inventory/inventory.api.js
 * ======================================================
 *
 * INVENTORY API (STAFF)
 * ------------------------------------------------------
 * Focus (V1):
 * - Expiry Alerts (store-scoped)
 *
 * Backend endpoint:
 * - GET /products/stock-batches/alerts/expiring-soon/?days=30&store_id=...
 *
 * Notes:
 * - Store-scoped filtering is REQUIRED for multi-store correctness.
 * - Backend is source of truth for expiry + stock.
 * - We normalize error messages to keep UI actionable.
 * ======================================================
 */

import axiosClient from "../../api/axiosClient";

function extractErrorMessage(err, fallback = "Request failed.") {
  const data = err?.response?.data;
  const status = err?.response?.status;

  // Our normalized backend errors:
  // {"error": {"code": "...", "message": "..."}}
  if (data?.error && typeof data.error === "object") {
    const msg = String(data.error.message || "").trim();
    if (msg) return status ? `[${status}] ${msg}` : msg;
  }

  // DRF common shapes
  if (typeof data?.detail === "string" && data.detail.trim()) {
    return status ? `[${status}] ${data.detail}` : data.detail;
  }

  // {field: ["msg"]} or {field: "msg"}
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const keys = Object.keys(data);
    if (keys.length) {
      const k = keys[0];
      const v = data[k];
      if (Array.isArray(v) && v[0]) {
        return status ? `[${status}] ${k}: ${v[0]}` : `${k}: ${v[0]}`;
      }
      if (typeof v === "string" && v.trim()) {
        return status ? `[${status}] ${k}: ${v}` : `${k}: ${v}`;
      }
    }
  }

  if (!data) return status ? `[${status}] ${err?.message || fallback}` : err?.message || fallback;
  if (typeof data === "string") return status ? `[${status}] ${data}` : data;

  return status ? `[${status}] ${fallback}` : fallback;
}

/**
 * Fetch expiring stock batches within N days.
 *
 * Backend returns:
 * - { count, results: [...] }
 *
 * @param {Object} params
 * @param {string} params.storeId - required
 * @param {number} [params.days=30] - non-negative integer
 */
export async function fetchExpiringSoon({ storeId, days = 30 }) {
  try {
    const sid = String(storeId || "").trim();
    if (!sid) throw new Error("storeId is required");

    const n = Number(days);
    const safeDays = Number.isFinite(n) ? Math.max(0, Math.floor(n)) : 30;

    const res = await axiosClient.get("/products/stock-batches/alerts/expiring-soon/", {
      params: {
        store_id: sid,
        days: safeDays,
      },
    });

    return res.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch expiring soon batches."));
  }
}
