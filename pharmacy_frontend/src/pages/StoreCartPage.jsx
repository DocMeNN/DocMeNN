// src/pages/StoreCartPage.jsx
/**
 * STORE CART PAGE (PUBLIC)
 * Route: /store/:storeId/cart
 *
 * Notes:
 * - This remains valid. It routes to /checkout.
 * - Paystack redirect happens in StoreCheckoutPage now.
 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { formatMoney } from "../utils/money";
import {
  readPublicCart,
  setPublicCartItemQty,
  removeFromPublicCart,
  clearPublicCart,
  computePublicCartSubtotal,
  countPublicCartItems,
} from "../lib/publicCart";
import { fetchPublicProducts } from "../features/pos/pos.api";

export default function StoreCartPage() {
  const { storeId } = useParams();
  const navigate = useNavigate();

  const [tick, setTick] = useState(0); // force re-read localStorage
  const [validating, setValidating] = useState(false);
  const [notice, setNotice] = useState("");
  const [warn, setWarn] = useState("");

  const bump = () => setTick((n) => n + 1);

  const cart = useMemo(() => readPublicCart(storeId), [storeId, tick]);
  const items = Array.isArray(cart?.items) ? cart.items : [];

  const itemCount = useMemo(() => countPublicCartItems(storeId), [storeId, tick]);
  const subtotal = useMemo(() => computePublicCartSubtotal(storeId), [storeId, tick]);

  useEffect(() => {
    let mounted = true;

    async function sanitizeCart() {
      if (!storeId) return;

      setWarn("");
      setNotice("");
      setValidating(true);

      try {
        const products = await fetchPublicProducts({ storeId, q: "" });
        const list = Array.isArray(products) ? products : [];

        const stockById = new Map(
          list.map((p) => [String(p.id), Number(p.total_stock || 0)])
        );

        const current = readPublicCart(storeId);
        const currentItems = Array.isArray(current?.items) ? current.items : [];

        if (currentItems.length === 0) {
          if (mounted) setNotice("");
          return;
        }

        let removed = 0;
        let clamped = 0;

        for (const it of currentItems) {
          const pid = String(it.product_id || "");
          const qty = Math.max(0, Number(it.quantity || 0));
          const available = stockById.has(pid) ? Number(stockById.get(pid) || 0) : 0;

          if (available <= 0) {
            removeFromPublicCart(storeId, pid);
            removed += 1;
            continue;
          }

          if (qty > available) {
            setPublicCartItemQty(storeId, pid, available);
            clamped += 1;
          }
        }

        if (!mounted) return;

        if (removed || clamped) {
          const parts = [];
          if (removed) parts.push(`${removed} out-of-stock item(s) removed`);
          if (clamped) parts.push(`${clamped} item(s) adjusted to available stock`);
          setNotice(`Cart updated: ${parts.join(" • ")}.`);
          bump();
        } else {
          setNotice("");
        }
      } catch (e) {
        if (!mounted) return;
        setWarn(e?.message || "Could not validate stock right now.");
      } finally {
        if (mounted) setValidating(false);
      }
    }

    sanitizeCart();

    return () => {
      mounted = false;
    };
  }, [storeId, tick]);

  if (!storeId) {
    return (
      <div className="rounded-2xl border bg-white p-6">
        <h1 className="text-xl font-semibold">Cart</h1>
        <p className="text-gray-600 mt-2">No store selected.</p>
        <button
          type="button"
          onClick={() => navigate("/store")}
          className="mt-4 px-4 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800"
        >
          Choose a Store
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">Your Cart</h1>
          <p className="text-sm text-gray-600 mt-1">
            Store: <span className="font-mono">{storeId}</span>
          </p>
          {validating ? (
            <p className="text-xs text-gray-500 mt-1">Validating stock…</p>
          ) : null}
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => navigate(`/store/${storeId}/shop`)}
            className="px-4 py-2 rounded-md border hover:bg-gray-50"
          >
            Continue shopping
          </button>

          <button
            type="button"
            onClick={() => {
              clearPublicCart(storeId);
              bump();
            }}
            className="px-4 py-2 rounded-md border hover:bg-gray-50"
            disabled={items.length === 0}
          >
            Clear cart
          </button>
        </div>
      </div>

      {(notice || warn) && (
        <div
          className={`border rounded p-3 text-sm ${
            warn
              ? "border-amber-200 bg-amber-50 text-amber-900"
              : "border-green-200 bg-green-50 text-green-800"
          }`}
        >
          {warn || notice}
        </div>
      )}

      <div className="rounded-2xl border bg-white">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="font-semibold">Items</div>
          <div className="text-sm text-gray-600">
            {itemCount} item{itemCount === 1 ? "" : "s"}
          </div>
        </div>

        {items.length === 0 ? (
          <div className="p-6 text-gray-600">
            Your cart is empty.
            <div className="mt-4">
              <button
                type="button"
                onClick={() => navigate(`/store/${storeId}/shop`)}
                className="px-4 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800"
              >
                Browse products
              </button>
            </div>
          </div>
        ) : (
          <div className="p-4 space-y-3">
            {items.map((it) => {
              const qty = Math.max(0, Number(it.quantity || 0));
              const unit = Number(it.unit_price || 0);
              const lineTotal = unit * qty;

              return (
                <div
                  key={it.product_id}
                  className="border rounded-xl p-4 flex items-start justify-between gap-4 flex-wrap"
                >
                  <div className="min-w-[220px]">
                    <div className="font-semibold text-gray-900">{it.name}</div>
                    <div className="text-sm text-gray-600">{formatMoney(unit)}</div>
                    {it.sku && (
                      <div className="text-xs text-gray-500 mt-1">
                        SKU: <span className="font-mono">{it.sku}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      className="px-3 py-2 rounded-md border hover:bg-gray-50"
                      onClick={() => {
                        const nextQty = qty - 1;
                        if (nextQty <= 0) {
                          removeFromPublicCart(storeId, it.product_id);
                        } else {
                          setPublicCartItemQty(storeId, it.product_id, nextQty);
                        }
                        bump();
                      }}
                      aria-label="Decrease quantity"
                    >
                      −
                    </button>

                    <div className="w-12 text-center font-medium">{qty}</div>

                    <button
                      type="button"
                      className="px-3 py-2 rounded-md border hover:bg-gray-50"
                      onClick={() => {
                        setPublicCartItemQty(storeId, it.product_id, qty + 1);
                        bump();
                      }}
                      aria-label="Increase quantity"
                    >
                      +
                    </button>

                    <button
                      type="button"
                      className="px-3 py-2 rounded-md border hover:bg-gray-50"
                      onClick={() => {
                        removeFromPublicCart(storeId, it.product_id);
                        bump();
                      }}
                    >
                      Remove
                    </button>
                  </div>

                  <div className="text-right min-w-[160px]">
                    <div className="text-sm text-gray-600">Line total</div>
                    <div className="font-semibold">{formatMoney(lineTotal)}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="rounded-2xl border bg-white p-5 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="text-sm text-gray-600">Subtotal</div>
          <div className="text-2xl font-bold">{formatMoney(subtotal)}</div>
          <div className="text-xs text-gray-500 mt-1">
            Cart is now sanitized against backend stock before checkout.
          </div>
        </div>

        <button
          type="button"
          disabled={items.length === 0 || validating}
          onClick={() => navigate(`/store/${storeId}/checkout`)}
          className="px-5 py-3 rounded-md bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
        >
          {validating ? "Validating…" : "Proceed to checkout"}
        </button>
      </div>
    </div>
  );
}