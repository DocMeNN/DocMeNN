/**
 * ======================================================
 * PATH: src/features/pos/pos.api.js
 * ======================================================
 *
 * POS API CONTRACT (STORE-SCOPED)
 * + PUBLIC SHOP CONTRACT (AllowAny, STORE-SCOPED)
 * ======================================================
 *
 * Staff endpoints (auth):
 * - GET  /store/stores/
 * - GET  /products/products/ (store_id optional but recommended)
 * - POST /products/products/ (create product)
 * - GET  /products/categories/ (category list)
 * - POST /products/categories/ (create category)
 * - POST /products/stock-batches/ (purchase-led stock intake => creates batch + receipt movement)
 * - GET  /products/stock-batches/ (list, filters: store_id, product_id)
 *
 * Public endpoints (AllowAny):
 * - GET  /store/stores/public/
 * - GET  /products/products/public/?store_id=&q=
 *
 * Legacy V1 (unsafe for card payments):
 * - POST /public/checkout/
 * - GET  /public/receipt/<sale_id>/
 *
 * Phase 4 (Paystack-safe):
 * - POST /public/order/initiate/
 * - GET  /public/order/<order_id>/
 * - POST /public/payments/paystack/webhook/
 * ======================================================
 */

import axiosClient from "../../api/axiosClient";

function extractErrorMessage(err, fallback = "Request failed.") {
  const data = err?.response?.data;
  const status = err?.response?.status;

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
      if (Array.isArray(v) && v[0]) {
        return status ? `[${status}] ${k}: ${v[0]}` : `${k}: ${v[0]}`;
      }
      if (typeof v === "string" && v.trim()) {
        return status ? `[${status}] ${k}: ${v}` : `${k}: ${v}`;
      }
    }
  }

  if (!data)
    return status
      ? `[${status}] ${err?.message || fallback}`
      : err?.message || fallback;

  if (typeof data === "string") return status ? `[${status}] ${data}` : data;

  return status ? `[${status}] ${fallback}` : fallback;
}

export function resolveStoreId(explicitStoreId) {
  const s =
    String(explicitStoreId || "").trim() ||
    String(localStorage.getItem("active_store_id") || "").trim() ||
    String(localStorage.getItem("store_id") || "").trim();

  return s || null;
}

function normalizeList(data) {
  const list = Array.isArray(data)
    ? data
    : Array.isArray(data?.results)
    ? data.results
    : null;

  return list || null;
}

function normalizeListToResults(data) {
  const list = normalizeList(data);
  if (!list) throw new Error("Invalid list response shape");

  const count = Number.isFinite(Number(data?.count))
    ? Number(data.count)
    : list.length;

  return {
    count,
    results: list,
    next: data?.next ?? null,
    previous: data?.previous ?? null,
  };
}

function normalizeProductsPayload(payload) {
  const list = normalizeList(payload);
  if (!list) return null;

  return list.map((p) => ({
    ...p,
    total_stock: p?.total_stock ?? p?.stock ?? p?.available_stock ?? p?.quantity ?? 0,
  }));
}

function normalizeCart(cart) {
  const safe = cart && typeof cart === "object" ? cart : {};
  const itemsRaw = Array.isArray(safe.items) ? safe.items : [];

  const items = itemsRaw.map((it) => {
    const productId = it?.product_id ?? it?.product ?? null;
    return { ...it, product_id: productId };
  });

  const subtotal_amount = safe.subtotal_amount ?? safe.total_amount ?? "0.00";
  const total_amount = safe.total_amount ?? safe.subtotal_amount ?? "0.00";
  const item_count = safe.item_count ?? items.length;

  return { ...safe, items, subtotal_amount, total_amount, item_count };
}

function normalizeAllocations(allocs) {
  if (!Array.isArray(allocs)) return null;

  const cleaned = allocs
    .map((a) => {
      const method = String(a?.method || a?.payment_method || "").trim();
      const amount = Number(a?.amount);
      return {
        method,
        amount: Number.isFinite(amount) ? amount : NaN,
      };
    })
    .filter((a) => a.method && Number.isFinite(a.amount) && a.amount > 0);

  return cleaned.length ? cleaned : null;
}

// ======================================================
// STORES
// ======================================================

export async function fetchStaffStores() {
  try {
    const res = await axiosClient.get("/store/stores/");
    const list = normalizeList(res.data);
    if (!list) throw new Error("Invalid stores response");

    return list.map((s) => ({
      id: s.id,
      name: s.name,
      is_active: s.is_active ?? true,
    }));
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch staff stores."));
  }
}

export async function fetchPublicStores() {
  try {
    const res = await axiosClient.get("/store/stores/public/");
    const list = normalizeList(res.data);
    if (!list) throw new Error("Invalid public stores response");

    return list.map((s) => ({
      id: s.id,
      name: s.name,
      is_active: s.is_active ?? true,
    }));
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch public stores."));
  }
}

export const fetchStores = fetchStaffStores;

// ======================================================
// CATEGORIES (STAFF)
// ======================================================

export async function fetchCategories() {
  try {
    const res = await axiosClient.get("/products/categories/");
    const list = normalizeList(res.data);
    if (!list) throw new Error("Invalid categories response");

    return list.map((c) => ({
      id: c.id,
      name: c.name,
    }));
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch categories."));
  }
}

export async function createCategory({ name } = {}) {
  try {
    const n = String(name || "").trim();
    if (!n) throw new Error("Category name is required.");

    const res = await axiosClient.post("/products/categories/", { name: n });

    if (!res.data || typeof res.data !== "object") {
      throw new Error("Categories API: Invalid create response");
    }

    return res.data; // expects {id, name, ...}
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to create category."));
  }
}

// ======================================================
// PRODUCTS (STAFF + PUBLIC)
// ======================================================

export async function fetchProducts({ storeId } = {}) {
  try {
    const resolvedStoreId = resolveStoreId(storeId);

    const res = await axiosClient.get("/products/products/", {
      params: resolvedStoreId ? { store_id: resolvedStoreId } : undefined,
    });

    const normalized = normalizeProductsPayload(res.data);
    if (!normalized) throw new Error("POS API: Invalid products response shape");

    return normalized;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch products."));
  }
}

export async function fetchPublicProducts({ storeId, q = "" } = {}) {
  try {
    const resolvedStoreId = String(storeId || "").trim();
    if (!resolvedStoreId)
      throw new Error("storeId is required for public products.");

    const res = await axiosClient.get("/products/products/public/", {
      params: {
        store_id: resolvedStoreId,
        q: String(q || "").trim() || undefined,
      },
    });

    const normalized = normalizeProductsPayload(res.data);
    if (!normalized)
      throw new Error("Public API: Invalid products response shape");

    return normalized;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch public products."));
  }
}

export async function createProduct(payload = {}, { storeId } = {}) {
  try {
    if (!payload || typeof payload !== "object") {
      throw new Error("Invalid product payload.");
    }

    const sid = resolveStoreId(storeId);

    const sku = String(payload.sku || "").trim();
    const name = String(payload.name || "").trim();
    if (!sku) throw new Error("sku is required.");
    if (!name) throw new Error("name is required.");

    const body = { ...payload };

    if (sid && !body.store) body.store = sid;

    if (!body.store) {
      throw new Error(
        "No active store selected. Set active_store_id before creating products."
      );
    }

    const res = await axiosClient.post("/products/products/", body);

    if (!res.data || typeof res.data !== "object") {
      throw new Error("Products API: Invalid create response");
    }

    return res.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to create product."));
  }
}

// ======================================================
// STOCK BATCH (PURCHASE-LED INTAKE)
// ======================================================

export async function intakeStockBatch({
  productId,
  quantity_received,
  unit_cost,
  expiry_date,
  batch_number,
} = {}) {
  try {
    const pid = String(productId || "").trim();
    if (!pid) throw new Error("productId is required.");

    const qty = Number(quantity_received);
    if (!Number.isFinite(qty) || qty <= 0)
      throw new Error("quantity_received must be > 0");

    const cost = Number(unit_cost);
    if (!Number.isFinite(cost) || cost <= 0)
      throw new Error("unit_cost must be > 0");

    const exp = String(expiry_date || "").trim();
    if (!exp) throw new Error("expiry_date is required (YYYY-MM-DD).");

    const payload = {
      product_id: pid,
      quantity_received: Math.floor(qty),
      unit_cost: String(cost.toFixed(2)),
      expiry_date: exp,
      ...(String(batch_number || "").trim()
        ? { batch_number: String(batch_number).trim() }
        : {}),
    };

    const res = await axiosClient.post("/products/stock-batches/", payload);

    if (!res.data || typeof res.data !== "object") {
      throw new Error("Stock intake: Invalid response");
    }

    return res.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to intake stock batch."));
  }
}

export async function fetchStockBatches({ storeId, productId, include_inactive } = {}) {
  try {
    const sid = resolveStoreId(storeId);

    const params = {
      ...(sid ? { store_id: sid } : {}),
      ...(productId ? { product_id: productId } : {}),
      ...(include_inactive !== undefined ? { include_inactive } : {}),
    };

    const res = await axiosClient.get("/products/stock-batches/", {
      params: Object.keys(params).length ? params : undefined,
    });

    return normalizeListToResults(res.data);
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch stock batches."));
  }
}

// ======================================================
// PUBLIC CHECKOUT (LEGACY V1 - UNSAFE FOR CARD)
// ======================================================

export async function publicCheckout(payload) {
  try {
    const res = await axiosClient.post("/public/checkout/", payload);
    return res.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Checkout failed."));
  }
}

export async function fetchPublicReceipt(saleId) {
  try {
    if (!saleId) throw new Error("saleId is required.");
    const res = await axiosClient.get(`/public/receipt/${saleId}/`);
    return res.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch receipt."));
  }
}

// ======================================================
// PUBLIC CHECKOUT (PHASE 4 - PAYSTACK SAFE)
// ======================================================

export async function publicOrderInitiate(payload) {
  try {
    const res = await axiosClient.post("/public/order/initiate/", payload);
    return res.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Payment initiation failed."));
  }
}

export async function fetchPublicOrderStatus(orderId) {
  try {
    if (!orderId) throw new Error("orderId is required.");
    const res = await axiosClient.get(`/public/order/${orderId}/`);
    return res.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch order status."));
  }
}

// ======================================================
// CART (STAFF POS)
// ======================================================

export async function fetchCart({ storeId } = {}) {
  try {
    const resolvedStoreId = resolveStoreId(storeId);
    if (!resolvedStoreId)
      throw new Error("store_id is required for POS cart operations.");

    const res = await axiosClient.get("/pos/cart/", {
      params: { store_id: resolvedStoreId },
    });

    if (!res.data || typeof res.data !== "object") {
      throw new Error("POS API: Invalid cart response");
    }

    return normalizeCart(res.data);
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to fetch cart."));
  }
}

export async function clearCart({ storeId } = {}) {
  try {
    const resolvedStoreId = resolveStoreId(storeId);
    if (!resolvedStoreId) throw new Error("store_id is required to clear cart.");

    const res = await axiosClient.delete("/pos/cart/clear/", {
      params: { store_id: resolvedStoreId },
    });

    if (!res.data || typeof res.data !== "object") {
      throw new Error("POS API: Invalid clear cart response");
    }

    return normalizeCart(res.data);
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to clear cart."));
  }
}

export async function addItemToCart({ storeId, productId, quantity = 1 }) {
  try {
    const resolvedStoreId = resolveStoreId(storeId);
    if (!resolvedStoreId) throw new Error("store_id is required.");
    if (!productId) throw new Error("productId is required.");

    const qty = Number(quantity);
    if (!Number.isFinite(qty) || qty <= 0)
      throw new Error("quantity must be a positive number");

    const res = await axiosClient.post("/pos/cart/items/add/", {
      store_id: resolvedStoreId,
      product_id: productId,
      quantity: Math.floor(qty),
    });

    if (!res.data || typeof res.data !== "object") {
      throw new Error("POS API: Invalid cart mutation response");
    }

    return normalizeCart(res.data);
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to add item."));
  }
}

export async function updateCartItemQuantity({ storeId, itemId, quantity }) {
  try {
    const resolvedStoreId = resolveStoreId(storeId);
    if (!resolvedStoreId) throw new Error("store_id is required.");
    if (!itemId) throw new Error("itemId is required.");

    const qty = Number(quantity);
    if (!Number.isFinite(qty) || qty < 1)
      throw new Error("quantity must be >= 1");

    const res = await axiosClient.patch(`/pos/cart/items/${itemId}/update/`, {
      store_id: resolvedStoreId,
      quantity: Math.floor(qty),
    });

    if (!res.data || typeof res.data !== "object") {
      throw new Error("POS API: Invalid update item response");
    }

    return normalizeCart(res.data);
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to update item quantity."));
  }
}

export async function removeItemFromCart({ storeId, itemId }) {
  try {
    const resolvedStoreId = resolveStoreId(storeId);
    if (!resolvedStoreId) throw new Error("store_id is required.");
    if (!itemId) throw new Error("itemId is required for removal.");

    const res = await axiosClient.delete(`/pos/cart/items/${itemId}/remove/`, {
      params: { store_id: resolvedStoreId },
    });

    if (!res.data || typeof res.data !== "object") {
      throw new Error("POS API: Invalid remove item response");
    }

    return normalizeCart(res.data);
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Failed to remove item."));
  }
}

// ======================================================
// CHECKOUT (STAFF POS)
// ======================================================

export async function checkoutCart({
  storeId,
  payment_method = "cash",
  payment_allocations,
} = {}) {
  try {
    const resolvedStoreId = resolveStoreId(storeId);
    if (!resolvedStoreId) throw new Error("store_id is required for checkout.");

    const allocations = normalizeAllocations(payment_allocations);
    const hasAllocations = Boolean(allocations);

    const payload = {
      store_id: resolvedStoreId,
      payment_method: hasAllocations ? "split" : payment_method,
      ...(hasAllocations ? { payment_allocations: allocations } : {}),
    };

    if (String(payment_method || "").toLowerCase() === "split" && !hasAllocations) {
      throw new Error("payment_allocations are required for split payment.");
    }

    const res = await axiosClient.post("/pos/checkout/", payload);

    if (!res.data || typeof res.data !== "object") {
      throw new Error("POS API: Checkout returned invalid response");
    }

    return res.data;
  } catch (err) {
    throw new Error(extractErrorMessage(err, "Checkout failed."));
  }
}