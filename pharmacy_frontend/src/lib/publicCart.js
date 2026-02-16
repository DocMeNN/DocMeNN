// src/lib/publicCart.js

/**
 * ======================================================
 * PUBLIC CART UTILITIES (STORE-SCOPED, LOCAL ONLY)
 * ------------------------------------------------------
 * Purpose:
 * - Manage public (unauthenticated) shopping cart
 * - Stored in localStorage
 * - One cart per store
 *
 * Rules:
 * - NO JSX
 * - NO React
 * - NO backend calls
 * - Pure, deterministic JavaScript
 * ======================================================
 */

function getCartKey(storeId) {
  if (!storeId) return null;
  return `public_cart:${storeId}`;
}

// --------------------------------------
// Read / Write
// --------------------------------------
export function readPublicCart(storeId) {
  const key = getCartKey(storeId);
  if (!key) return { items: [] };

  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : null;
    const items = Array.isArray(parsed?.items) ? parsed.items : [];
    return { items };
  } catch {
    return { items: [] };
  }
}

export function writePublicCart(storeId, cart) {
  const key = getCartKey(storeId);
  if (!key) return;

  try {
    localStorage.setItem(key, JSON.stringify(cart));
  } catch {
    // ignore quota / serialization errors
  }
}

// --------------------------------------
// Mutations
// --------------------------------------
export function addToPublicCart(storeId, product, qty = 1) {
  const cart = readPublicCart(storeId);
  const items = [...cart.items];

  const safeQty = Math.max(1, Math.floor(Number(qty) || 1));

  const index = items.findIndex(
    (it) => String(it.product_id) === String(product.id)
  );

  if (index >= 0) {
    items[index] = {
      ...items[index],
      quantity: Number(items[index].quantity || 0) + safeQty,
    };
  } else {
    items.push({
      product_id: product.id,
      name: product.name,
      unit_price: product.unit_price,
      sku: product.sku,
      barcode: product.barcode,
      quantity: safeQty,
    });
  }

  const next = { items };
  writePublicCart(storeId, next);
  return next;
}

export function setPublicCartItemQty(storeId, productId, qty) {
  const safeQty = Math.max(0, Math.floor(Number(qty) || 0));

  const cart = readPublicCart(storeId);
  const items = cart.items
    .map((it) =>
      String(it.product_id) === String(productId)
        ? { ...it, quantity: safeQty }
        : it
    )
    .filter((it) => Number(it.quantity || 0) > 0);

  const next = { items };
  writePublicCart(storeId, next);
  return next;
}

export function removeFromPublicCart(storeId, productId) {
  const cart = readPublicCart(storeId);
  const items = cart.items.filter(
    (it) => String(it.product_id) !== String(productId)
  );

  const next = { items };
  writePublicCart(storeId, next);
  return next;
}

export function clearPublicCart(storeId) {
  const key = getCartKey(storeId);
  if (!key) return;

  try {
    localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

// --------------------------------------
// Derived helpers
// --------------------------------------
export function countPublicCartItems(storeId) {
  const cart = readPublicCart(storeId);
  return cart.items.reduce((sum, it) => sum + Number(it.quantity || 0), 0);
}

export function computePublicCartSubtotal(storeId) {
  const cart = readPublicCart(storeId);
  return cart.items.reduce((sum, it) => {
    const qty = Number(it.quantity || 0);
    const price = Number(it.unit_price || 0);
    return sum + qty * price;
  }, 0);
}

/**
 * ======================================================
 * CHECKOUT PAYLOAD (backend serializer truth)
 * ------------------------------------------------------
 * Backend expects:
 * {
 *   store_id: "...",
 *   payment_method: "online",
 *   items: [{ product_id: "...", quantity: 2 }]
 * }
 * ======================================================
 */
export function buildPublicCheckoutPayload(storeId, { payment_method = "online" } = {}) {
  const sid = String(storeId || "").trim();
  if (!sid) {
    return { store_id: null, payment_method, items: [] };
  }

  const cart = readPublicCart(sid);
  const items = Array.isArray(cart?.items) ? cart.items : [];

  const normalized = items
    .map((it) => {
      const productId = it?.product_id ?? it?.productId ?? it?.id;
      const qty = Math.floor(Number(it?.quantity || 0));
      return {
        product_id: productId ? String(productId) : null,
        quantity: qty,
      };
    })
    .filter((it) => it.product_id && Number.isFinite(it.quantity) && it.quantity > 0);

  return {
    store_id: sid,
    payment_method,
    items: normalized,
  };
}

/**
 * Remove items that are now out-of-stock based on latest backend product list.
 * products should be the list returned by fetchPublicProducts()
 */
export function sanitizePublicCartAgainstProducts(storeId, products = []) {
  const sid = String(storeId || "").trim();
  if (!sid) return { items: [] };

  const byId = new Map(
    (Array.isArray(products) ? products : []).map((p) => [String(p.id), p])
  );

  const cart = readPublicCart(sid);
  const items = (Array.isArray(cart?.items) ? cart.items : []).filter((it) => {
    const pid = String(it?.product_id || "");
    const p = byId.get(pid);

    // If we can’t find the product anymore, remove it (stale)
    if (!p) return false;

    // If out of stock now, remove it
    const stock = Number(p.total_stock ?? 0);
    if (!Number.isFinite(stock) || stock <= 0) return false;

    return Number(it.quantity || 0) > 0;
  });

  const next = { items };
  writePublicCart(sid, next);
  return next;
}
