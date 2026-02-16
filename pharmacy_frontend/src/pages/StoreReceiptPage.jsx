// src/pages/StoreReceiptPage.jsx

/**
 * STORE RECEIPT PAGE (PUBLIC)
 *
 * Route: /store/:storeId/receipt/:saleId
 *
 * Purpose:
 * - Fetch receipt from backend: GET /api/public/receipt/<sale_id>/
 * - Render totals + (optional) items if backend provides them
 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { formatMoney } from "../utils/money";
import { fetchPublicReceipt } from "../features/pos/pos.api";

export default function StoreReceiptPage() {
  const { storeId, saleId } = useParams();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [data, setData] = useState(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      setLoading(true);
      setErr("");
      try {
        const res = await fetchPublicReceipt(saleId);
        if (mounted) setData(res);
      } catch (e) {
        if (mounted) setErr(e?.message || "Failed to load receipt.");
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, [saleId]);

  const sale = useMemo(() => {
    if (!data) return null;
    // supports either {sale: {...}} or direct sale object {...}
    return data?.sale && typeof data.sale === "object" ? data.sale : data;
  }, [data]);

  const items = useMemo(() => {
    // supports either {items: []} or sale.items if backend later includes it
    if (Array.isArray(data?.items)) return data.items;
    if (Array.isArray(sale?.items)) return sale.items;
    return [];
  }, [data, sale]);

  if (loading) return <div className="p-6 text-gray-600">Loading receipt…</div>;

  if (err) {
    return (
      <div className="rounded-2xl border bg-white p-6">
        <h1 className="text-xl font-semibold">Receipt</h1>
        <div className="mt-4 border rounded p-3 text-sm border-red-200 bg-red-50 text-red-800">
          {err}
        </div>
        <button
          type="button"
          onClick={() => navigate(`/store/${storeId}/shop`)}
          className="mt-4 px-4 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800"
        >
          Back to shop
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-white p-6">
        <h1 className="text-2xl font-semibold">Receipt</h1>
        <p className="text-sm text-gray-600 mt-1">
          Store: <span className="font-mono">{storeId}</span>
        </p>

        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div className="rounded-xl border p-4 bg-gray-50">
            <div className="text-gray-600">Invoice</div>
            <div className="font-mono font-semibold">{sale?.invoice_no || "—"}</div>
          </div>
          <div className="rounded-xl border p-4 bg-gray-50">
            <div className="text-gray-600">Total</div>
            <div className="text-xl font-bold">
              {formatMoney(Number(sale?.total_amount || 0))}
            </div>
          </div>
        </div>

        <div className="mt-4 text-xs text-gray-500">
          Status: <span className="font-mono">{sale?.status || "—"}</span>
        </div>
      </div>

      <div className="rounded-2xl border bg-white">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="font-semibold">Items</div>
          <div className="text-sm text-gray-600">{items.length} line(s)</div>
        </div>

        {items.length === 0 ? (
          <div className="p-6 text-gray-600">
            Items are not included in this receipt response yet.
          </div>
        ) : (
          <div className="p-4 space-y-3">
            {items.map((it, idx) => (
              <div
                key={it.id || `${it.product_id || "line"}-${idx}`}
                className="border rounded-xl p-4 flex items-start justify-between gap-4"
              >
                <div>
                  <div className="font-semibold text-gray-900">
                    {it.product_name || it.name || "Item"}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    Qty: <span className="font-mono">{it.quantity}</span>
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-sm text-gray-600">Line total</div>
                  <div className="font-semibold">
                    {formatMoney(Number(it.total_price || 0))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => navigate(`/store/${storeId}/shop`)}
          className="px-4 py-2 rounded-md border hover:bg-gray-50"
        >
          Continue shopping
        </button>
      </div>
    </div>
  );
}
