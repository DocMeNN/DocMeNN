/**
 * ======================================================
 * PATH: src/pages/PosPage.jsx
 * ======================================================
 *
 * POS PAGE — PAYMENT UX POLISH (FRONTEND)
 * ------------------------------------------------------
 * Golden rules enforced here:
 * - NEVER use float math for money; use cents (kobo) in UI.
 * - Backend is authority; frontend prevents avoidable 400s.
 *
 * Store Scope:
 * - StoreSelector now lives in DashboardLayout.
 * - POS listens for store switch events:
 *    window event: "active-store-changed"
 *
 * Split rules:
 * - sum(allocations) must equal total (2dp exact)
 * - each allocation amount > 0
 *
 * UX:
 * - Confirm button disabled unless split is valid
 * - Receipt preview modal before final submit
 *
 * After checkout:
 * - Navigate to staff receipt route:
 *   /pos/:storeId/receipt/:saleId
 * ======================================================
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchProducts } from "../features/pos/pos.api";
import { usePosStore } from "../stores/posStore";
import { formatMoney } from "../utils/money";

import CartPanel from "../features/pos/CartPanel";
import CheckoutBar from "../features/pos/CheckoutBar";

const PAYMENT_METHODS = [
  { value: "cash", label: "Cash" },
  { value: "bank", label: "Bank" },
  { value: "pos", label: "POS" },
  { value: "transfer", label: "Transfer" },
  { value: "credit", label: "Credit" },
];

// ---------- Money helpers (safe cents math) ----------
function toCents(value) {
  const s = String(value ?? "").trim();
  if (!s) return 0;
  const normalized = s.replace(/,/g, "");
  const n = Number(normalized);
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 100);
}

function centsToAmountString(cents) {
  const v = Math.round(Number(cents || 0));
  return (v / 100).toFixed(2);
}

function sumCents(lines) {
  return (lines || []).reduce((acc, x) => acc + (Number(x?.amountCents) || 0), 0);
}

function clampNonNegInt(n) {
  const x = Number(n || 0);
  if (!Number.isFinite(x)) return 0;
  return Math.max(0, Math.round(x));
}

// ---------- Modal (no external deps) ----------
function Modal({ open, title, children, onClose }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden="true" />
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div className="w-full max-w-2xl rounded-xl bg-white shadow-lg border">
          <div className="flex items-center justify-between px-5 py-4 border-b">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
            </div>
            <button type="button" className="px-3 py-1 rounded border text-sm" onClick={onClose}>
              Close
            </button>
          </div>

          <div className="p-5">{children}</div>
        </div>
      </div>
    </div>
  );
}

function SplitPaymentEditor({ totalAmount, allocations, setAllocations }) {
  const totalCents = useMemo(() => toCents(totalAmount), [totalAmount]);
  const allocatedCents = useMemo(() => sumCents(allocations), [allocations]);
  const remainingCents = totalCents - allocatedCents;

  const updateLine = (idx, patch) => {
    setAllocations((prev) => prev.map((x, i) => (i === idx ? { ...x, ...patch } : x)));
  };

  const addLine = () => {
    setAllocations((prev) => [
      ...(prev || []),
      { method: "cash", amountCents: 0, reference: "", note: "" },
    ]);
  };

  const removeLine = (idx) => {
    setAllocations((prev) => prev.filter((_, i) => i !== idx));
  };

  const fillRemaining = (idx) => {
    if (remainingCents <= 0) return;
    const current = clampNonNegInt(allocations?.[idx]?.amountCents);
    const newCents = clampNonNegInt(current + remainingCents);
    updateLine(idx, { amountCents: newCents });
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-white p-4">
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-600">Total Due</p>
          <p className="text-lg font-semibold">{formatMoney(totalAmount)}</p>
        </div>

        <div className="flex items-center justify-between mt-2">
          <p className="text-sm text-gray-600">Allocated</p>
          <p className="text-sm font-medium">{formatMoney(centsToAmountString(allocatedCents))}</p>
        </div>

        <div className="flex items-center justify-between mt-1">
          <p className="text-sm text-gray-600">Remaining</p>
          <p
            className={`text-sm font-medium ${
              remainingCents === 0 ? "text-green-700" : "text-red-700"
            }`}
          >
            {formatMoney(centsToAmountString(remainingCents))}
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {(allocations || []).map((a, idx) => (
          <div key={idx} className="rounded-lg border bg-white p-4 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div>
                <label className="text-xs text-gray-500">Method</label>
                <select
                  className="w-full border rounded-md px-3 py-2"
                  value={a.method || "cash"}
                  onChange={(e) => updateLine(idx, { method: e.target.value })}
                >
                  {PAYMENT_METHODS.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs text-gray-500">Amount</label>
                <input
                  className="w-full border rounded-md px-3 py-2"
                  inputMode="decimal"
                  value={centsToAmountString(a.amountCents || 0)}
                  onChange={(e) => updateLine(idx, { amountCents: toCents(e.target.value) })}
                />
              </div>

              <div>
                <label className="text-xs text-gray-500">Reference</label>
                <input
                  className="w-full border rounded-md px-3 py-2"
                  value={a.reference || ""}
                  onChange={(e) => updateLine(idx, { reference: e.target.value })}
                  placeholder="Optional"
                />
              </div>

              <div>
                <label className="text-xs text-gray-500">Note</label>
                <input
                  className="w-full border rounded-md px-3 py-2"
                  value={a.note || ""}
                  onChange={(e) => updateLine(idx, { note: e.target.value })}
                  placeholder="Optional"
                />
              </div>
            </div>

            <div className="flex gap-2 justify-between">
              <button
                type="button"
                className="text-sm px-3 py-2 rounded-md border disabled:opacity-50"
                onClick={() => fillRemaining(idx)}
                disabled={remainingCents <= 0}
              >
                Fill Remaining
              </button>

              <button
                type="button"
                className="text-sm px-3 py-2 rounded-md border text-red-700 disabled:opacity-50"
                onClick={() => removeLine(idx)}
                disabled={(allocations || []).length <= 1}
              >
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>

      <button
        type="button"
        className="w-full px-4 py-3 rounded-md bg-gray-900 text-white"
        onClick={addLine}
      >
        Add Payment Line
      </button>
    </div>
  );
}

export default function PosPage() {
  const { storeId: routeStoreId } = useParams();
  const navigate = useNavigate();

  const [products, setProducts] = useState([]);
  const [barcode, setBarcode] = useState("");
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  // Payment UI state
  const [payModalOpen, setPayModalOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [payMode, setPayMode] = useState("single"); // "single" | "split"
  const [singleMethod, setSingleMethod] = useState("cash");
  const [allocations, setAllocations] = useState([
    { method: "cash", amountCents: 0, reference: "", note: "" },
  ]);
  const [payUiError, setPayUiError] = useState("");

  const barcodeRef = useRef(null);

  const {
    activeStoreId,
    loadStores,
    setActiveStore,
    cart,
    loading,
    isLocked,
    loadCart,
    mutateItem,
    checkout,
    clearActiveCart,
  } = usePosStore();

  const locked = isLocked();
  const storeReady = !!activeStoreId;

  const cartItems = Array.isArray(cart?.items) ? cart.items : [];
  const cartHasItems = cartItems.length > 0;

  const cartTotalAmount = cart?.total_amount ?? cart?.subtotal_amount ?? 0;

  const { bySku, byBarcode } = useMemo(() => {
    const skuMap = new Map();
    const barcodeMap = new Map();

    for (const p of products || []) {
      const sku = p?.sku != null ? String(p.sku).trim() : "";
      const bc = p?.barcode != null ? String(p.barcode).trim() : "";

      if (sku) skuMap.set(sku, p);
      if (bc) barcodeMap.set(bc, p);
    }

    return { bySku: skuMap, byBarcode: barcodeMap };
  }, [products]);

  const focusBarcode = () => {
    setTimeout(() => barcodeRef.current?.focus(), 0);
  };

  const clearMessages = () => {
    setError("");
    setStatus("");
  };

  function resolveSid() {
    return (
      String(activeStoreId || "").trim() ||
      String(routeStoreId || "").trim() ||
      String(localStorage.getItem("active_store_id") || "").trim() ||
      ""
    );
  }

  async function reloadProductsForStore(sid) {
    const safe = String(sid || "").trim();
    if (!safe) {
      setProducts([]);
      return;
    }
    const prods = await fetchProducts({ storeId: safe });
    setProducts(Array.isArray(prods) ? prods : []);
  }

  async function hydrateStoreContext(sid, label = "Ready.") {
    const safe = String(sid || "").trim();
    if (!safe) {
      setProducts([]);
      setStatus("Select a store to begin.");
      return;
    }

    clearMessages();
    await setActiveStore(safe);
    await reloadProductsForStore(safe);
    await loadCart();
    setStatus(label);
  }

  // ------------------------------------------------------
  // Boot
  // ------------------------------------------------------
  useEffect(() => {
    async function boot() {
      setBooting(true);
      clearMessages();

      try {
        await loadStores();

        const sid =
          String(routeStoreId || "").trim() ||
          String(localStorage.getItem("active_store_id") || "").trim() ||
          "";

        if (sid) {
          await hydrateStoreContext(
            sid,
            routeStoreId ? "Store selected from URL. Ready." : "Ready."
          );
        } else {
          setProducts([]);
          setStatus("Select a store to begin.");
        }
      } catch (e) {
        setError(e?.message || "Failed to load POS data. Check connection and try again.");
      } finally {
        setBooting(false);
        focusBarcode();
      }
    }

    boot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------------------------------------------------------
  // Listen for DashboardLayout store changes
  // ------------------------------------------------------
  useEffect(() => {
    const handler = async (evt) => {
      const sid = String(evt?.detail?.storeId || "").trim();
      if (!sid) return;

      try {
        setStatus("Switching store…");
        await hydrateStoreContext(sid, "Ready.");
      } catch (e) {
        setError(e?.message || "Failed to load data for selected store.");
      } finally {
        focusBarcode();
      }
    };

    window.addEventListener("active-store-changed", handler);
    return () => window.removeEventListener("active-store-changed", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep barcode input focused whenever we unlock the POS
  useEffect(() => {
    if (!locked) focusBarcode();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locked]);

  // Keep split allocations sensible when cart total changes
  useEffect(() => {
    if (payMode !== "split") return;
    const totalCents = toCents(cartTotalAmount);
    const allocated = sumCents(allocations);
    const allZero = (allocations || []).every((a) => (Number(a?.amountCents) || 0) === 0);

    if (totalCents > 0 && allocated === 0 && allZero) {
      setAllocations((prev) => {
        const base =
          Array.isArray(prev) && prev.length
            ? prev
            : [{ method: "cash", amountCents: 0, reference: "", note: "" }];
        return base.map((x, i) => (i === 0 ? { ...x, amountCents: totalCents } : x));
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cartTotalAmount, payMode]);

  const resolveProductFromScan = (raw) => {
    const code = String(raw || "").trim();
    if (!code) return null;
    return bySku.get(code) || byBarcode.get(code) || null;
  };

  const handleBarcodeAdd = async () => {
    if (locked) return;

    if (!storeReady) {
      setError("Select a store first.");
      return;
    }

    const code = String(barcode || "").trim();
    if (!code) {
      setError("Scan a barcode or enter a SKU.");
      focusBarcode();
      return;
    }

    clearMessages();

    const found = resolveProductFromScan(code);
    if (!found) {
      setError(`No product found for: "${code}"`);
      setBarcode("");
      focusBarcode();
      return;
    }

    if (Number(found.total_stock || 0) <= 0) {
      setError(`Out of stock: ${found.name}`);
      setBarcode("");
      focusBarcode();
      return;
    }

    try {
      await mutateItem(found.id, 1);
      setStatus(`Added: ${found.name}`);
    } catch (e) {
      setError(e?.message || "Failed to add item to cart.");
    } finally {
      setBarcode("");
      focusBarcode();
    }
  };

  const handleIncrement = async (item) => {
    if (locked) return;
    if (!storeReady) {
      setError("Select a store first.");
      return;
    }
    clearMessages();
    try {
      await mutateItem(item.product_id ?? item.product?.id, 1);
    } catch (e) {
      setError(e?.message || "Failed to add item.");
    } finally {
      focusBarcode();
    }
  };

  const handleDecrement = async (item) => {
    if (locked) return;
    if (!storeReady) {
      setError("Select a store first.");
      return;
    }
    clearMessages();
    try {
      await mutateItem(item.product_id ?? item.product?.id, -1);
    } catch (e) {
      setError(e?.message || "Failed to reduce item quantity.");
    } finally {
      focusBarcode();
    }
  };

  const handleCheckout = async () => {
    if (locked) return;

    if (!storeReady) {
      setError("Select a store first.");
      return;
    }

    clearMessages();

    if (!cartHasItems) {
      setError("Cart is empty. Add items before checkout.");
      focusBarcode();
      return;
    }

    setPayUiError("");
    setPayModalOpen(true);
    setPreviewOpen(false);
  };

  const closePayModal = () => {
    setPayModalOpen(false);
    setPreviewOpen(false);
    setPayUiError("");
  };

  const validateSplitAllocations = () => {
    const totalCents = toCents(cartTotalAmount);
    const legs = allocations || [];

    if (!legs.length) return "Add at least one payment line.";

    for (let i = 0; i < legs.length; i++) {
      const m = String(legs[i]?.method || "").trim().toLowerCase();
      if (!PAYMENT_METHODS.some((x) => x.value === m)) return `Invalid method on line ${i + 1}.`;
      const amt = clampNonNegInt(legs[i]?.amountCents);
      if (amt <= 0) return `Amount must be > 0 on line ${i + 1}.`;
    }

    const allocated = sumCents(legs);
    if (allocated !== totalCents) {
      return `Split payment must match total exactly. Remaining: ${formatMoney(
        centsToAmountString(totalCents - allocated)
      )}`;
    }

    return null;
  };

  const splitValidationMsg = useMemo(() => {
    if (payMode !== "split") return null;
    return validateSplitAllocations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payMode, allocations, cartTotalAmount]);

  const canConfirm = !locked && cartHasItems && (payMode === "single" ? true : !splitValidationMsg);

  const openPreview = () => {
    setPayUiError("");
    if (payMode === "split") {
      if (splitValidationMsg) {
        setPayUiError(splitValidationMsg);
        return;
      }
    }
    setPreviewOpen(true);
  };

  const performCheckout = async () => {
    if (locked) return;

    setPayUiError("");

    try {
      let data = null;

      if (payMode === "split") {
        const errMsg = validateSplitAllocations();
        if (errMsg) {
          setPayUiError(errMsg);
          return;
        }

        const payloadAllocations = (allocations || []).map((a) => ({
          method: String(a.method || "").trim().toLowerCase(),
          amount: centsToAmountString(a.amountCents),
          reference: String(a.reference || "").trim(),
          note: String(a.note || "").trim(),
        }));

        data = await checkout("split", payloadAllocations);
      } else {
        data = await checkout(singleMethod);
      }

      if (!data) throw new Error("Checkout succeeded but no response payload returned.");

      const total =
        data.total_amount ??
        data.subtotal_amount ??
        cart?.total_amount ??
        cart?.subtotal_amount ??
        0;

      const saleId =
        data?.id || data?.sale?.id || data?.sale_id || data?.saleId || null;

      const sid = resolveSid();

      await loadCart();
      await reloadProductsForStore(sid);

      setStatus(`Checkout successful • Total: ${formatMoney(total)}`);
      setBarcode("");
      closePayModal();
      focusBarcode();

      if (!saleId) {
        setError("Checkout completed, but sale id was not returned. Check backend response.");
        return;
      }
      if (!sid) {
        setError("Checkout completed, but store id is missing. Select a store and try again.");
        return;
      }

      navigate(`/pos/${sid}/receipt/${saleId}`, { replace: true });
    } catch (e) {
      setPayUiError(e?.message || "Checkout failed.");
    }
  };

  const handleClearCart = async () => {
    if (locked) return;

    if (!storeReady) {
      setError("Select a store first.");
      return;
    }

    clearMessages();
    try {
      await clearActiveCart();
      await loadCart();
      setStatus("New sale started. Cart cleared.");
    } catch (e) {
      setError(e?.message || "Failed to clear cart.");
    } finally {
      focusBarcode();
    }
  };

  if (booting || loading) {
    return <p className="p-6">Loading POS…</p>;
  }

  const previewAllocations =
    payMode === "split"
      ? (allocations || []).map((a) => ({
          method: String(a.method || "").trim().toLowerCase(),
          amount: centsToAmountString(a.amountCents),
          reference: a.reference || "",
          note: a.note || "",
        }))
      : null;

  const itemRows = cartItems;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="space-y-2">
          <div>
            <h1 className="text-2xl font-bold">Point of Sale</h1>
            <p className="text-sm text-gray-600">
              {locked ? "Locked (processing…)" : storeReady ? "Ready for sales" : "Select a store"}
            </p>
          </div>

          <div className="text-xs text-gray-500">
            Active store:{" "}
            <span className="font-semibold text-gray-900">{activeStoreId || "— not set —"}</span>
          </div>
        </div>

        <div className="text-right text-sm text-gray-600">
          <div>Products: {products.length}</div>
          <div>
            Cart items: {cart?.item_count ?? (Array.isArray(cart?.items) ? cart.items.length : 0)}
          </div>
          <div className="mt-1 font-medium">Total: {formatMoney(cartTotalAmount)}</div>
        </div>
      </div>

      {(error || status) && (
        <div
          className={`border rounded p-3 text-sm ${
            error ? "border-red-200 bg-red-50 text-red-800" : "border-green-200 bg-green-50 text-green-800"
          }`}
        >
          {error || status}
        </div>
      )}

      {/* Barcode add */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          ref={barcodeRef}
          className="border px-3 py-2 rounded w-72"
          placeholder="Scan barcode or type SKU…"
          value={barcode}
          disabled={locked || !storeReady}
          inputMode="numeric"
          autoComplete="off"
          onChange={(e) => setBarcode(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleBarcodeAdd();
          }}
        />
        <button
          disabled={locked || !storeReady}
          className="bg-green-600 text-white px-4 py-2 rounded disabled:opacity-50"
          onClick={handleBarcodeAdd}
        >
          Add
        </button>

        <button
          disabled={locked}
          className="border px-4 py-2 rounded disabled:opacity-50"
          onClick={() => {
            setBarcode("");
            clearMessages();
            focusBarcode();
          }}
        >
          Clear
        </button>
      </div>

      {/* Products */}
      <div>
        <h2 className="font-semibold mb-2">Products</h2>

        {products.length === 0 ? (
          <p className="text-gray-500">
            {storeReady ? "No products available for this store." : "Select a store to view products."}
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {products.map((p) => {
              const out = Number(p.total_stock || 0) <= 0;
              const btnDisabled = locked || !storeReady || out;

              return (
                <button
                  type="button"
                  key={p.id}
                  onClick={async () => {
                    if (btnDisabled) return;
                    clearMessages();
                    try {
                      await mutateItem(p.id, 1);
                      setStatus(`Added: ${p.name}`);
                    } catch (e) {
                      setError(e?.message || "Failed to add item.");
                    } finally {
                      focusBarcode();
                    }
                  }}
                  disabled={btnDisabled}
                  className="text-left border p-4 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <p className="font-medium">{p.name}</p>
                  <p className="text-sm text-gray-600">{formatMoney(p.unit_price)}</p>
                  <p className="text-xs text-gray-500">SKU: {p.sku}</p>
                  <p className="text-xs text-gray-500">
                    Stock: {p.total_stock} {out ? "• OUT" : ""}
                  </p>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Cart */}
      <div>
        <h2 className="font-semibold mb-2">Cart</h2>

        <CartPanel
          cart={cart}
          onIncrement={handleIncrement}
          onDecrement={handleDecrement}
          onClearCart={handleClearCart}
          disabled={locked || !storeReady}
        />

        {cartHasItems && (
          <CheckoutBar onCheckout={handleCheckout} disabled={locked || !storeReady} />
        )}
      </div>

      {/* Payment Modal */}
      <Modal
        open={payModalOpen}
        title={previewOpen ? "Receipt Preview" : "Payment"}
        onClose={() => {
          if (locked) return;
          closePayModal();
        }}
      >
        {!previewOpen ? (
          <div className="space-y-4">
            <div className="rounded-lg border bg-white p-4">
              <p className="text-sm text-gray-600">Amount Due</p>
              <p className="text-xl font-semibold mt-1">{formatMoney(cartTotalAmount)}</p>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className={`px-4 py-2 rounded border text-sm ${
                  payMode === "single" ? "bg-gray-900 text-white" : "bg-white"
                }`}
                onClick={() => {
                  setPayUiError("");
                  setPayMode("single");
                }}
              >
                Single Payment
              </button>

              <button
                type="button"
                className={`px-4 py-2 rounded border text-sm ${
                  payMode === "split" ? "bg-gray-900 text-white" : "bg-white"
                }`}
                onClick={() => {
                  setPayUiError("");
                  setPayMode("split");
                  setAllocations((prev) =>
                    Array.isArray(prev) && prev.length
                      ? prev
                      : [
                          {
                            method: "cash",
                            amountCents: toCents(cartTotalAmount),
                            reference: "",
                            note: "",
                          },
                        ]
                  );
                }}
              >
                Split Payment
              </button>
            </div>

            {payMode === "single" ? (
              <div className="rounded-lg border bg-white p-4 space-y-2">
                <label className="text-xs text-gray-500">Payment Method</label>
                <select
                  className="w-full border rounded-md px-3 py-2"
                  value={singleMethod}
                  onChange={(e) => setSingleMethod(e.target.value)}
                >
                  {PAYMENT_METHODS.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-2">
                  For split payment (cash + transfer + credit etc.), switch to “Split Payment”.
                </p>
              </div>
            ) : (
              <SplitPaymentEditor
                totalAmount={cartTotalAmount}
                allocations={allocations}
                setAllocations={setAllocations}
              />
            )}

            {payMode === "split" && splitValidationMsg && !payUiError && (
              <div className="border rounded p-3 text-sm border-amber-200 bg-amber-50 text-amber-900">
                {splitValidationMsg}
              </div>
            )}

            {payUiError && (
              <div className="border rounded p-3 text-sm border-red-200 bg-red-50 text-red-800">
                {payUiError}
              </div>
            )}

            <div className="flex gap-3 justify-end pt-2">
              <button
                type="button"
                className="px-4 py-2 rounded border"
                onClick={() => {
                  if (locked) return;
                  closePayModal();
                }}
                disabled={locked}
              >
                Cancel
              </button>

              <button
                type="button"
                className="px-5 py-2 rounded bg-gray-900 text-white disabled:opacity-50"
                onClick={openPreview}
                disabled={!canConfirm}
                title={payMode === "split" && splitValidationMsg ? "Fix split amounts to match total" : undefined}
              >
                Preview Receipt
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg border bg-white p-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-600">Total</p>
                <p className="text-lg font-semibold">{formatMoney(cartTotalAmount)}</p>
              </div>
              <div className="mt-2 text-xs text-gray-500">
                Store: {activeStoreId || "—"} • Items:{" "}
                {cart?.item_count ?? (Array.isArray(cart?.items) ? cart.items.length : 0)}
              </div>
            </div>

            <div className="rounded-lg border bg-white p-4">
              <p className="text-sm font-semibold mb-3">Items</p>
              {itemRows.length === 0 ? (
                <p className="text-sm text-gray-500">No items.</p>
              ) : (
                <div className="space-y-2">
                  {itemRows.map((it, idx) => {
                    const name =
                      it?.product_name ||
                      it?.name ||
                      it?.product?.name ||
                      `Item ${idx + 1}`;

                    const qty = Number(it?.quantity || 0);

                    const unit =
                      it?.unit_price ??
                      it?.unit_price_amount ??
                      it?.product?.unit_price ??
                      0;

                    const lineTotal =
                      it?.line_total ??
                      it?.total_amount ??
                      Number(unit || 0) * qty;

                    const key = it?.id ?? `${it?.product_id ?? it?.product?.id ?? "x"}-${idx}`;

                    return (
                      <div key={key} className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-medium truncate">{name}</p>
                          <p className="text-xs text-gray-500">
                            {qty} × {formatMoney(unit)}
                          </p>
                        </div>
                        <div className="text-sm font-medium">{formatMoney(lineTotal)}</div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="rounded-lg border bg-white p-4">
              <p className="text-sm font-semibold mb-3">Payment</p>

              {payMode === "single" ? (
                <div className="flex items-center justify-between">
                  <p className="text-sm text-gray-600">Method</p>
                  <p className="text-sm font-medium">
                    {PAYMENT_METHODS.find((x) => x.value === singleMethod)?.label || singleMethod}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {(previewAllocations || []).map((a, idx) => (
                    <div key={idx} className="rounded-md border p-3 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium">
                          {PAYMENT_METHODS.find((x) => x.value === a.method)?.label || a.method}
                        </p>
                        {(a.reference || a.note) && (
                          <p className="text-xs text-gray-500 truncate">
                            {a.reference ? `Ref: ${a.reference}` : ""}
                            {a.reference && a.note ? " • " : ""}
                            {a.note ? `Note: ${a.note}` : ""}
                          </p>
                        )}
                      </div>
                      <div className="text-sm font-semibold">{formatMoney(a.amount)}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {payUiError && (
              <div className="border rounded p-3 text-sm border-red-200 bg-red-50 text-red-800">
                {payUiError}
              </div>
            )}

            <div className="flex flex-wrap gap-3 justify-end pt-2">
              <button
                type="button"
                className="px-4 py-2 rounded border"
                onClick={() => {
                  if (locked) return;
                  setPreviewOpen(false);
                }}
                disabled={locked}
              >
                Back
              </button>

              <button
                type="button"
                className="px-5 py-2 rounded bg-green-600 text-white disabled:opacity-50"
                onClick={performCheckout}
                disabled={!canConfirm}
              >
                Confirm & Checkout
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
