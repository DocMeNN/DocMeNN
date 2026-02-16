// src/pages/StoreOrderStatusPage.jsx
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchPublicOrderStatus } from "../features/pos/pos.api";
import { formatMoney } from "../utils/money";

export default function StoreOrderStatusPage() {
  const { storeId, orderId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [data, setData] = useState(null);

  const stoppedRef = useRef(false);

  const pretty = useMemo(() => {
    const status = String(data?.status || "—");
    const amount = Number(data?.amount || 0);
    const saleId = data?.sale_id || null;
    return { status, amount, saleId };
  }, [data]);

  useEffect(() => {
    if (!storeId || !orderId) return;

    stoppedRef.current = false;

    async function sleep(ms) {
      return new Promise((r) => setTimeout(r, ms));
    }

    async function poll() {
      setErr("");
      setLoading(true);

      const maxAttempts = 60; // ~2.5 mins at 2.5s
      const baseIntervalMs = 2500;

      for (let i = 0; i < maxAttempts; i += 1) {
        if (stoppedRef.current) return;

        try {
          const res = await fetchPublicOrderStatus(orderId);
          if (stoppedRef.current) return;

          setData(res);

          const saleId = res?.sale_id || null;
          const status = String(res?.status || "").toLowerCase();

          // ✅ Success: sale exists => receipt
          if (saleId) {
            navigate(`/store/${storeId}/receipt/${saleId}`, { replace: true });
            return;
          }

          // ✅ Terminal failure states
          if (status === "cancelled" || status === "failed") {
            setErr("Order could not be completed. Payment was not confirmed. Please try again.");
            setLoading(false);
            return;
          }
        } catch (e) {
          if (stoppedRef.current) return;
          setErr(e?.message || "Could not fetch order status.");
          // keep polling; transient network/provider delays are normal
        }

        // gentle backoff to reduce server load
        const backoff = Math.min(2000, i * 50); // max +2s
        await sleep(baseIntervalMs + backoff);
      }

      if (!stoppedRef.current) {
        setLoading(false);
        setErr("Still processing payment. Please refresh this page in a moment.");
      }
    }

    poll();

    return () => {
      stoppedRef.current = true;
    };
  }, [storeId, orderId, navigate]);

  if (!storeId || !orderId) {
    return (
      <div className="rounded-2xl border bg-white p-6">
        <h1 className="text-xl font-semibold">Order Status</h1>
        <p className="text-gray-600 mt-2">Missing store or order reference.</p>
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

  const isPaid = String(pretty.status || "").toLowerCase() === "paid";
  const isPending = String(pretty.status || "").toLowerCase() === "pending_payment";
  const isProcessing = !isPaid && !pretty.saleId && !err;

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-white p-6">
        <h1 className="text-2xl font-semibold">
          {isPaid ? "Payment Confirmed" : isPending || isProcessing ? "Processing Payment" : "Order Status"}
        </h1>

        <p className="text-sm text-gray-600 mt-1">
          Store: <span className="font-mono">{storeId}</span>
        </p>
        <p className="text-sm text-gray-600 mt-1">
          Order: <span className="font-mono">{orderId}</span>
        </p>

        {err && (
          <div className="mt-4 border rounded p-3 text-sm border-red-200 bg-red-50 text-red-800">
            {err}
          </div>
        )}
      </div>

      <div className="rounded-2xl border bg-white p-5 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="text-sm text-gray-600">Status</div>
          <div className="text-xl font-bold">{pretty.status}</div>
          <div className="text-xs text-gray-500 mt-1">
            Amount: <span className="font-mono">{formatMoney(pretty.amount)}</span>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="px-4 py-2 rounded-md border hover:bg-gray-50"
          >
            Refresh
          </button>

          <button
            type="button"
            onClick={() => navigate(`/store/${storeId}/cart`)}
            className="px-4 py-2 rounded-md border hover:bg-gray-50"
          >
            Back to cart
          </button>
        </div>
      </div>

      {loading && (
        <div className="text-sm text-gray-600">
          Polling for confirmation… (this can take a few seconds)
        </div>
      )}
    </div>
  );
}