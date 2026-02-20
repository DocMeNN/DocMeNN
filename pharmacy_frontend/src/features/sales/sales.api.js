/**
 * ======================================================
 * PATH: src/features/sales/sales.api.js
 * ======================================================
 *
 * SALES API CONTRACT (STAFF)
 *
 * Endpoints (DRF router):
 * - LIST:   GET  /api/sales/sales/
 * - DETAIL: GET  /api/sales/sales/:id/
 * - REFUND: POST /api/sales/sales/:id/refund/
 *
 * Notes:
 * - Backend may return paginated {results: []} OR plain list [] depending on config.
 * - Refund supports:
 *   - FULL: omit items or items=[]
 *   - PARTIAL: items=[{sale_item_id, quantity}, ...]
 *
 * Golden rules:
 * - Backend is source of truth
 * - Fail-fast with readable error messages (prevents silent UI confusion)
 * ======================================================
 */

import axiosClient from "../../api/axiosClient";

function normalizeList(data) {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object" && Array.isArray(data.results)) return data.results;
  return [];
}

function extractErrorMessage(err, fallback = "Request failed.") {
  const status = err?.response?.status;
  const data = err?.response?.data;

  if (data?.error && typeof data.error === "object") {
    const msg = String(data.error.message || "").trim();
    if (msg) return status ? `[${status}] ${msg}` : msg;
  }

  if (typeof data?.detail === "string" && data.detail.trim()) {
    return status ? `[${status}] ${data.detail}` : data.detail;
  }

  if (data && typeof data === "object" && !Array.isArray(data)) {
    const keys = Object.keys(data);
    if (keys.length) {
      const k = keys[0];
      const v = data[k];
      if (Array.isArray(v) && v[0])
        return status ? `[${status}] ${k}: ${v[0]}` : `${k}: ${v[0]}`;
      if (typeof v === "string" && v.trim())
        return status ? `[${status}] ${k}: ${v}` : `${k}: ${v}`;
    }
  }

  if (!data)
    return status ? `[${status}] ${err?.message || fallback}` : err?.message || fallback;

  if (typeof data === "string") return status ? `[${status}] ${data}` : data;

  return status ? `[${status}] ${fallback}` : fallback;
}

function resolveActiveStoreId() {
  return String(localStorage.getItem("active_store_id") || "").trim() || null;
}

export async function fetchSales({ storeId } = {}) {
  try {
    const sid = String(storeId || "").trim() || resolveActiveStoreId();
    const params = sid ? { store_id: sid } : undefined;

    const res = await axiosClient.get("/sales/sales/", { params });
    return normalizeList(res.data);
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch sales."));
  }
}

export async function fetchSaleById(saleId) {
  try {
    const sid = String(saleId || "").trim();
    if (!sid) throw new Error("Sale ID is required.");

    const res = await axiosClient.get(`/sales/sales/${sid}/`);

    if (!res.data || typeof res.data !== "object") throw new Error("Invalid sale response.");

    // Some serializers may return {sale:{...}} — accept both and return the sale object
    const sale =
      res.data?.sale && typeof res.data.sale === "object" ? res.data.sale : res.data;

    if (!sale?.id) throw new Error("Invalid sale response (missing id).");

    return sale;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch sale."));
  }
}

export async function refundSale(saleId, payload = {}) {
  try {
    const sid = String(saleId || "").trim();
    if (!sid) throw new Error("Sale ID is required for refund.");

    const body = {};

    const reason = payload?.reason ? String(payload.reason).trim() : "";
    if (reason) body.reason = reason;

    if (Array.isArray(payload?.items)) {
      body.items = payload.items; // FULL: [] or omit; PARTIAL: [{sale_item_id, quantity}]
    }

    const res = await axiosClient.post(`/sales/sales/${sid}/refund/`, body);

    if (!res.data || typeof res.data !== "object") {
      throw new Error("Refund failed (invalid response).");
    }

    if (res.data?.detail && String(res.data.detail).toLowerCase().includes("failed")) {
      throw new Error(String(res.data.detail));
    }

    return res.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Refund failed."));
  }
}
