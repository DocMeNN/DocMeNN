/**
 * PATH: src/pages/StoreCheckoutPage.jsx
 *
 * STORE CHECKOUT PAGE (PUBLIC) — PAYSTACK SAFE (PHASE 4)
 *
 * Route: /store/:storeId/checkout
 *
 * Purpose:
 * - Read localStorage public cart
 * - POST to backend /api/public/order/initiate/
 * - Redirect user to Paystack authorization_url (hosted)
 *
 * After payment:
 * - Paystack hits webhook -> backend finalizes Sale
 * - Frontend polls /api/public/order/<order_id>/ until sale_id exists
 *
 * GOLDEN RULE:
 * Ask for the file → you paste → I return a complete final file for copy & replace.
 */

import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { formatMoney } from "../utils/money";
import { readPublicCart, computePublicCartSubtotal } from "../lib/publicCart";
import { publicOrderInitiate } from "../features/pos/pos.api";

export default function StoreCheckoutPage() {
  const { storeId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const cart = useMemo(() => readPublicCart(storeId), [storeId]);
  const items = Array.isArray(cart?.items) ? cart.items : [];
  const subtotal = useMemo(() => computePublicCartSubtotal(storeId), [storeId]);

  async function placeOrder() {
    const sid = String(storeId || "").trim();
    if (!sid) return;

    setErr("");

    if (items.length === 0) {
      setErr("Your cart is empty.");
      return;
    }

    setLoading(true);
    try {
      const payloadItems = items.map((it) => ({
        product_id: it.product_id,
        quantity: Number(it.quantity || 0),
      }));

      // ✅ BACKEND EXPECTS: store_id (NOT storeId)
      const res = await publicOrderInitiate({
        store_id: sid,
        items: payloadItems,
        customer_name: String(cart?.customer_name || "").trim() || undefined,
        customer_phone: String(cart?.customer_phone || "").trim() || undefined,
        customer_email: String(cart?.customer_email || "").trim() || undefined,
      });

      const orderId = res?.order_id || null;
      const authorizationUrl = String(res?.authorization_url || "").trim();

      if (!orderId) throw new Error("Order initiation succeeded but order_id is missing.");
      if (!authorizationUrl) throw new Error("Payment initiation succeeded but authorization_url is missing.");

      // Save for recovery (refresh/back button scenarios)
      try {
        localStorage.setItem(`public_order:${sid}:last_order_id`, String(orderId));
        localStorage.setItem(`public_order:${sid}:last_reference`, String(res?.reference || ""));
      } catch (_) {}

      // Redirect to Paystack hosted payment page
      window.location.assign(authorizationUrl);
    } catch (e) {
      setErr(e?.message || "Checkout failed.");
      setLoading(false);
    }
  }

  if (!storeId) {
    return (
      <div className="rounded-2xl border bg-white p-6">
        <h1 className="text-xl font-semibold">Checkout</h1>
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
      <div className="rounded-2xl border bg-white p-6">
        <h1 className="text-2xl font-semibold">Checkout</h1>
        <p className="text-sm text-gray-600 mt-1">
          Store: <span className="font-mono">{storeId}</span>
        </p>

        {err && (
          <div className="mt-4 border rounded p-3 text-sm border-red-200 bg-red-50 text-red-800">
            {err}
          </div>
        )}
      </div>

      <div className="rounded-2xl border bg-white">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="font-semibold">Order Summary</div>
          <div className="text-sm text-gray-600">{items.length} item(s)</div>
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
            {items.map((it) => (
              <div
                key={it.product_id}
                className="border rounded-xl p-4 flex items-start justify-between gap-4"
              >
                <div>
                  <div className="font-semibold text-gray-900">{it.name}</div>
                  <div className="text-sm text-gray-600">{formatMoney(it.unit_price)}</div>
                  <div className="text-xs text-gray-500 mt-1">
                    Qty: <span className="font-mono">{it.quantity}</span>
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-sm text-gray-600">Line total</div>
                  <div className="font-semibold">
                    {formatMoney(Number(it.unit_price || 0) * Number(it.quantity || 0))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-2xl border bg-white p-5 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="text-sm text-gray-600">Subtotal</div>
          <div className="text-2xl font-bold">{formatMoney(subtotal)}</div>
          <div className="text-xs text-gray-500 mt-1">
            Backend will re-validate stock + pricing during order initiation.
          </div>
        </div>

        <button
          type="button"
          disabled={loading || items.length === 0}
          onClick={placeOrder}
          className="px-5 py-3 rounded-md bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
        >
          {loading ? "Redirecting to payment…" : "Pay with Paystack"}
        </button>
      </div>
    </div>
  );
}