// src/api/products.js

/**
 * ======================================================
 * PATH: src/api/products.js
 * ======================================================
 *
 * PRODUCTS API CONTRACT (STAFF)
 *
 * Goals:
 * - Store-scoped when possible (store_id from:
 *   1) explicit argument
 *   2) localStorage.active_store_id
 *   3) localStorage.store_id (legacy)
 * )
 * - Optionally ENFORCE store selection via requireStore=true
 * - Supports BOTH list shapes:
 *   1) [] (non-paginated)
 *   2) { count, next, previous, results: [] } (paginated)
 * - Exposes:
 *   - resolveStoreId()
 *   - fetchProducts()
 *   - fetchCategories()
 *   - createProduct()
 *
 * NOTE:
 * - Your backend ProductViewSet.list() may ignore some filters unless implemented
 *   (e.g. q/include_inactive). We keep them as forward-compatible parameters.
 */

import axiosClient from "./axiosClient";

function extractErrorMessage(err, fallback = "Request failed.") {
  const data = err?.response?.data;
  const status = err?.response?.status;

  // Normalized backend errors:
  // {"error": {"code": "...", "message": "..." }}
  if (data?.error && typeof data.error === "object") {
    const msg = String(data.error.message || "").trim();
    if (msg) return status ? `[${status}] ${msg}` : msg;
  }

  // DRF common shape
  if (typeof data?.detail === "string" && data.detail.trim()) {
    return status ? `[${status}] ${data.detail}` : data.detail;
  }

  // Field errors: {field: ["msg"]} or {field: "msg"}
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

  if (!data) {
    return status ? `[${status}] ${err?.message || fallback}` : err?.message || fallback;
  }
  if (typeof data === "string") return status ? `[${status}] ${data}` : data;

  return status ? `[${status}] ${fallback}` : fallback;
}

/**
 * Resolve staff store context from:
 * 1) explicit argument
 * 2) active_store_id (preferred)
 * 3) store_id (legacy fallback)
 */
export function resolveStoreId(explicitStoreId) {
  const s =
    String(explicitStoreId || "").trim() ||
    String(localStorage.getItem("active_store_id") || "").trim() ||
    String(localStorage.getItem("store_id") || "").trim();

  return s || null;
}

function normalizeListToResults(data) {
  // Non-paginated
  if (Array.isArray(data)) {
    return { results: data, count: data.length, next: null, previous: null };
  }

  // Paginated
  if (data && typeof data === "object" && Array.isArray(data.results)) {
    return {
      results: data.results,
      count: Number.isFinite(Number(data.count)) ? Number(data.count) : data.results.length,
      next: data.next ?? null,
      previous: data.previous ?? null,
    };
  }

  throw new Error("Products API: Invalid response shape");
}

// ======================================================
// PRODUCTS
// ======================================================

/**
 * fetchProducts (STAFF)
 *
 * Options:
 * - storeId: explicit store id (optional)
 * - requireStore: if true => throws when no store is selected
 * - q: optional search term (forward-compatible; backend may ignore unless implemented)
 * - include_inactive: optional (forward-compatible; backend may ignore unless implemented)
 */
export async function fetchProducts({ storeId, requireStore = false, q, include_inactive } = {}) {
  try {
    const sid = resolveStoreId(storeId);

    if (requireStore && !sid) {
      throw new Error("No active store selected. Please set active_store_id first.");
    }

    const params = {
      ...(sid ? { store_id: sid } : {}),
      ...(q ? { q: String(q).trim() } : {}),
      ...(include_inactive !== undefined ? { include_inactive } : {}),
    };

    const res = await axiosClient.get("/products/products/", {
      params: Object.keys(params).length ? params : undefined,
    });

    return normalizeListToResults(res?.data);
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch products."));
  }
}

/**
 * createProduct (STAFF)
 *
 * Enforces store context for multi-store correctness.
 * If store cannot be resolved, we fail fast.
 */
export async function createProduct(payload = {}, { storeId } = {}) {
  try {
    const sid = resolveStoreId(storeId);

    const body = { ...(payload || {}) };

    // Enforce store context if available
    if (sid && !body.store) {
      body.store = sid;
    }

    // Fail fast if still no store (multi-store correctness)
    if (!body.store) {
      throw new Error("No store selected. Please select an active store before creating products.");
    }

    const res = await axiosClient.post("/products/products/", body);

    if (!res?.data || typeof res.data !== "object") {
      throw new Error("Products API: Invalid create product response");
    }

    return res.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to create product."));
  }
}

// ======================================================
// CATEGORIES
// ======================================================

export async function fetchCategories() {
  try {
    const res = await axiosClient.get("/products/categories/");
    return normalizeListToResults(res?.data);
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch categories."));
  }
}
