// src/stores/posStore.js

/**
 * ======================================================
 * PATH: src/stores/posStore.js
 * ======================================================
 *
 * POS Store (MULTI-STORE SAFE) + SPLIT PAYMENT SUPPORT
 *
 * Split Payment Rule (Frontend enforcement):
 * - If payment_allocations is provided:
 *   - it must be a non-empty array
 *   - each amount must be > 0
 *   - sum(amount) must equal cart total (2dp exact)
 * - If provided, backend will set payment_method="split"
 *
 * NOTE (Store selection ownership):
 * - Store selection UI lives in DashboardLayout (sets localStorage.active_store_id
 *   and dispatches "active-store-changed").
 * - This store provides setActiveStore(), but DOES NOT auto-fetch cart by default.
 *   Pages should call loadCart()/refreshCart() after selecting a store.
 */

import { create } from "zustand";
import {
  fetchStaffStores,
  fetchCart,
  clearCart,
  addItemToCart,
  updateCartItemQuantity,
  removeItemFromCart,
  checkoutCart,
  resolveStoreId,
} from "../features/pos/pos.api";

// ------------------------------
// Money helpers (NO FLOAT TRAPS)
// ------------------------------
function toCents(v) {
  const s = String(v ?? "").trim();
  if (!s) return 0;
  const normalized = s.replace(/,/g, "");
  const n = Number(normalized);
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 100);
}

function centsToAmountString(cents) {
  const c = Math.round(Number(cents || 0));
  return (c / 100).toFixed(2);
}

function sumCents(lines) {
  // lines are normalized to have `.amount` as a string like "12.00"
  return (lines || []).reduce((acc, x) => acc + (toCents(x?.amount) || 0), 0);
}

function normalizeMethod(m) {
  return String(m || "").trim().toLowerCase();
}

const ALLOWED_METHODS = new Set(["cash", "bank", "pos", "transfer", "credit"]);

function normalizeAllocations(input) {
  if (!input) return null;
  if (!Array.isArray(input)) throw new Error("payment_allocations must be an array.");

  const out = input
    .map((a) => ({
      method: normalizeMethod(a?.method),
      // accept amount as string/number; normalize to "12.00"
      amount: centsToAmountString(toCents(a?.amount)),
      reference: String(a?.reference || ""),
      note: String(a?.note || ""),
    }))
    .filter((a) => a.method && toCents(a.amount) > 0);

  if (!out.length) throw new Error("Split payment requires at least one valid allocation line.");

  for (const a of out) {
    if (!ALLOWED_METHODS.has(a.method)) {
      throw new Error(`Invalid payment allocation method: ${a.method}`);
    }
    if (toCents(a.amount) <= 0) {
      throw new Error("Each split payment allocation amount must be > 0.");
    }
  }

  return out;
}

export const usePosStore = create((set, get) => ({
  // --------------------------------------
  // Store context + stores list
  // --------------------------------------
  activeStoreId: resolveStoreId(),
  stores: [],
  storesLoading: false,

  // --------------------------------------
  // Store-scoped carts
  // --------------------------------------
  cartsByStore: {}, // { [storeId]: cart }
  cart: null, // derived “current store cart” for UI convenience

  // --------------------------------------
  // POS state
  // --------------------------------------
  loading: false,
  isMutating: false,
  isCheckingOut: false,
  isClearing: false,
  lastError: "",

  _refreshPromisesByStore: {}, // { [storeId]: Promise }

  // --------------------------------------
  // Guards
  // --------------------------------------
  isLocked: () => get().isMutating || get().isCheckingOut || get().isClearing,

  canCheckout: () => {
    const { cart } = get();
    const hasItems = !!(cart && Array.isArray(cart.items) && cart.items.length > 0);
    return hasItems && !get().isLocked();
  },

  // --------------------------------------
  // Helpers
  // --------------------------------------
  _setError: (msg) => set({ lastError: msg || "" }),

  _requireStoreId: () => {
    const sid = String(get().activeStoreId || "").trim() || null;
    if (!sid) throw new Error("No active store selected. Please choose a store first.");
    return sid;
  },

  _setCartForStore: (storeId, cart) => {
    const sid = String(storeId || "").trim();
    if (!sid) return;

    set((state) => {
      const nextMap = { ...(state.cartsByStore || {}) };
      nextMap[sid] = cart || null;

      const isActive = String(state.activeStoreId || "").trim() === sid;
      return {
        cartsByStore: nextMap,
        cart: isActive ? (cart || null) : state.cart,
      };
    });
  },

  _findCartItemByProductId: (productId) => {
    const items = Array.isArray(get().cart?.items) ? get().cart.items : [];
    const pid = String(productId || "");
    return items.find((it) => String(it?.product_id ?? it?.product ?? "") === pid) || null;
  },

  _getCartTotalForValidationCents: () => {
    const cart = get().cart || {};
    const total = cart.total_amount ?? cart.subtotal_amount ?? 0;
    return toCents(total);
  },

  // --------------------------------------
  // Store actions
  // --------------------------------------
  loadStores: async () => {
    set({ storesLoading: true });
    try {
      const stores = await fetchStaffStores();
      set({ stores: Array.isArray(stores) ? stores : [] });
      get()._setError("");
      return stores;
    } catch (err) {
      get()._setError(err?.message || "Failed to load stores.");
      throw err;
    } finally {
      set({ storesLoading: false });
    }
  },

  /**
   * setActiveStore(storeId, { refreshCart = false } = {})
   *
   * We default refreshCart=false to avoid double-fetches because:
   * - Pages often call setActiveStore() then loadCart()/refreshCart().
   */
  setActiveStore: async (storeId, { refreshCart = false } = {}) => {
    const sid = String(storeId || "").trim() || null;

    if (sid) localStorage.setItem("active_store_id", sid);
    else localStorage.removeItem("active_store_id");

    set((state) => ({
      activeStoreId: sid,
      cart: sid ? state.cartsByStore?.[sid] || null : null,
      lastError: "",
    }));

    if (sid && refreshCart) {
      await get().refreshCart({ storeId: sid });
    }
  },

  syncActiveStoreFromLocalStorage: () => {
    const sid = resolveStoreId();
    set((state) => ({
      activeStoreId: sid,
      cart: sid ? state.cartsByStore?.[sid] || null : null,
    }));
  },

  // --------------------------------------
  // Cart lifecycle (STORE-SCOPED)
  // --------------------------------------
  refreshCart: async ({ storeId } = {}) => {
    const sid = String(storeId || get().activeStoreId || resolveStoreId() || "").trim();

    if (!sid) {
      set({ cart: null });
      return null;
    }

    const existing = get()._refreshPromisesByStore?.[sid];
    if (existing) return existing;

    const p = (async () => {
      try {
        const cart = await fetchCart({ storeId: sid });
        get()._setCartForStore(sid, cart);
        get()._setError("");
        return cart;
      } catch (err) {
        get()._setError(err?.message || "Failed to refresh cart.");
        throw err;
      } finally {
        set((state) => {
          const next = { ...(state._refreshPromisesByStore || {}) };
          delete next[sid];
          return { _refreshPromisesByStore: next };
        });
      }
    })();

    set((state) => ({
      _refreshPromisesByStore: { ...(state._refreshPromisesByStore || {}), [sid]: p },
    }));

    return p;
  },

  loadCart: async () => {
    set({ loading: true });
    try {
      const sid = get()._requireStoreId();
      await get().refreshCart({ storeId: sid });
    } finally {
      set({ loading: false });
    }
  },

  // --------------------------------------
  // Cart mutations
  // --------------------------------------
  mutateItem: async (productId, delta) => {
    if (get().isLocked()) return;

    const d = Number(delta);
    if (!Number.isFinite(d) || d === 0) return;

    set({ isMutating: true });
    try {
      const storeId = get()._requireStoreId();

      if (d > 0) {
        await addItemToCart({
          storeId,
          productId,
          quantity: Math.floor(d),
        });
      } else {
        const item = get()._findCartItemByProductId(productId);
        if (!item) return;

        const currentQty = Number(item.quantity || 0);
        const nextQty = currentQty + d;

        if (nextQty <= 0) {
          await removeItemFromCart({ storeId, itemId: item.id });
        } else {
          await updateCartItemQuantity({
            storeId,
            itemId: item.id,
            quantity: nextQty,
          });
        }
      }

      await get().refreshCart({ storeId });
      get()._setError("");
    } catch (err) {
      get()._setError(err?.message || "Failed to update cart item.");
      throw err;
    } finally {
      set({ isMutating: false });
    }
  },

  clearActiveCart: async () => {
    if (get().isLocked()) return;

    set({ isClearing: true });
    try {
      const storeId = get()._requireStoreId();
      await clearCart({ storeId });
      await get().refreshCart({ storeId });
      get()._setError("");
    } catch (err) {
      get()._setError(err?.message || "Failed to clear cart.");
      throw err;
    } finally {
      set({ isClearing: false });
    }
  },

  // --------------------------------------
  // Checkout (supports split allocations)
  // --------------------------------------
  checkout: async (paymentMethod = "cash", paymentAllocations = null) => {
    if (get().isLocked()) return;
    if (!get().canCheckout()) return;

    set({ isCheckingOut: true });
    try {
      const storeId = get()._requireStoreId();

      const method = normalizeMethod(paymentMethod) || "cash";
      const allocs = normalizeAllocations(paymentAllocations);

      if (!allocs) {
        if (!ALLOWED_METHODS.has(method)) {
          throw new Error(`Invalid payment method: ${method}`);
        }
      }

      // Frontend enforcement for split totals (avoid backend 400s)
      if (allocs) {
        const cartTotalCents = get()._getCartTotalForValidationCents();
        const allocTotalCents = sumCents(allocs);

        if (allocTotalCents !== cartTotalCents) {
          const remaining = cartTotalCents - allocTotalCents;
          throw new Error(
            `Split payment must match cart total exactly. Remaining: ${centsToAmountString(
              remaining
            )}`
          );
        }
      }

      const result = await checkoutCart({
        storeId,
        payment_method: allocs ? "split" : method,
        payment_allocations: allocs || undefined,
      });

      await get().refreshCart({ storeId });
      get()._setError("");

      return result;
    } catch (err) {
      get()._setError(err?.message || "Checkout failed.");
      throw err;
    } finally {
      set({ isCheckingOut: false });
    }
  },

  reset: () => {
    set({
      activeStoreId: resolveStoreId(),
      stores: [],
      storesLoading: false,
      cartsByStore: {},
      cart: null,
      loading: false,
      isMutating: false,
      isCheckingOut: false,
      isClearing: false,
      lastError: "",
      _refreshPromisesByStore: {},
    });
  },
}));
