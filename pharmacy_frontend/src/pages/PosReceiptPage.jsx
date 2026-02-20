/**
 * ======================================================
 * PATH: src/pages/PosReceiptPage.jsx
 * ======================================================
 *
 * POS RECEIPT PAGE (STAFF)
 *
 * Route: /pos/:storeId/receipt/:saleId
 *
 * Purpose:
 * - Fetch a staff sale receipt using authenticated endpoints.
 * - Render a print-ready receipt (single + split).
 *
 * Design rules:
 * - Backend is authoritative for totals + allocations.
 * - store_id is passed where applicable (multi-store guard).
 * - We use CANONICAL receipt endpoint first, with 1 legacy fallback only.
 * ======================================================
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import axiosClient from "../api/axiosClient";
import { formatMoney } from "../utils/money";

function extractErrMessage(err, fallback = "Failed to fetch staff receipt.") {
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
      if (Array.isArray(v) && v[0]) {
        return status ? `[${status}] ${k}: ${v[0]}` : `${k}: ${v[0]}`;
      }
      if (typeof v === "string" && v.trim()) {
        return status ? `[${status}] ${k}: ${v}` : `${k}: ${v}`;
      }
    }
  }

  const msg = err?.message || fallback;
  return status ? `[${status}] ${msg}` : msg;
}

function toNumber(x, fallback = 0) {
  if (x == null || x === "") return fallback;
  const n = Number(String(x).replace(/,/g, ""));
  return Number.isFinite(n) ? n : fallback;
}

async function fetchStaffReceiptCanonical({ saleId, storeId }) {
  if (!saleId) throw new Error("saleId is required.");

  // ✅ Canonical first, then legacy alias (kept for older clients)
  const candidates = [`/sales/sales/${saleId}/receipt/`, `/sales/${saleId}/receipt/`];

  let lastErr = null;

  for (const url of candidates) {
    try {
      const res = await axiosClient.get(url, {
        params: storeId ? { store_id: storeId } : undefined,
      });

      if (res?.data && typeof res.data === "object") return res.data;
      lastErr = new Error("Invalid receipt response shape.");
    } catch (e) {
      lastErr = e;
    }
  }

  throw new Error(extractErrMessage(lastErr, "Failed to fetch staff receipt."));
}

export default function PosReceiptPage() {
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
        const res = await fetchStaffReceiptCanonical({ saleId, storeId });
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
  }, [saleId, storeId]);

  const sale = useMemo(() => {
    if (!data) return null;
    return data?.sale && typeof data.sale === "object" ? data.sale : data;
  }, [data]);

  const items = useMemo(() => {
    if (Array.isArray(data?.items)) return data.items;
    if (Array.isArray(sale?.items)) return sale.items;
    return [];
  }, [data, sale]);

  const allocations = useMemo(() => {
    const a =
      data?.payment_allocations ??
      sale?.payment_allocations ??
      data?.allocations ??
      sale?.allocations ??
      null;

    return Array.isArray(a) ? a : [];
  }, [data, sale]);

  const subtotal = toNumber(sale?.subtotal_amount ?? sale?.subtotal ?? 0);
  const tax = toNumber(sale?.tax_amount ?? sale?.tax ?? 0);
  const discount = toNumber(sale?.discount_amount ?? sale?.discount ?? 0);
  const total = toNumber(
    sale?.total_amount ?? sale?.total ?? subtotal + tax - discount
  );

  const invoiceNo = sale?.invoice_no || sale?.invoice || sale?.reference || "—";
  const status = sale?.status || "—";
  const paymentMethod = String(sale?.payment_method || "—").toUpperCase();

  const paidLegsSum = useMemo(() => {
    if (!allocations.length) return null;
    return allocations.reduce(
      (acc, a) => acc + toNumber(a?.amount ?? a?.amount_paid ?? 0),
      0
    );
  }, [allocations]);

  if (loading) return <div className="p-6 text-gray-600">Loading receipt…</div>;

  if (err) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <div className="rounded-2xl border bg-white p-6">
          <h1 className="text-xl font-semibold">Receipt</h1>
          <div className="mt-4 border rounded p-3 text-sm border-red-200 bg-red-50 text-red-800">
            {err}
          </div>

          <div className="mt-4 flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => navigate(`/pos/${storeId}`)}
              className="px-4 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800"
            >
              Back to POS
            </button>

            <Link
              to="/sales"
              className="px-4 py-2 rounded-md border hover:bg-gray-50"
            >
              Sales History
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <style>{`
        @media print {
          .no-print { display: none !important; }
          .print-wrap { box-shadow: none !important; border: none !important; }
          body { background: white !important; }
        }
      `}</style>

      <div className="rounded-2xl border bg-white p-6 print-wrap">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold">Receipt</h1>
            <p className="text-sm text-gray-600 mt-1">
              Store: <span className="font-mono">{storeId}</span>
            </p>
          </div>

          <div className="no-print flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => window.print()}
              className="px-4 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800"
            >
              Print
            </button>
            <button
              type="button"
              onClick={() => navigate(`/pos/${storeId}`)}
              className="px-4 py-2 rounded-md border hover:bg-gray-50"
            >
              Back to POS
            </button>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div className="rounded-xl border p-4 bg-gray-50">
            <div className="text-gray-600">Invoice</div>
            <div className="font-mono font-semibold">{invoiceNo}</div>
            <div className="text-xs text-gray-500 mt-2">
              Status: <span className="font-mono">{status}</span>
            </div>
          </div>

          <div className="rounded-xl border p-4 bg-gray-50">
            <div className="text-gray-600">Total</div>
            <div className="text-xl font-bold">{formatMoney(total)}</div>
            <div className="text-xs text-gray-500 mt-2">
              Payment:{" "}
              <span className="font-mono">
                {allocations.length ? "SPLIT" : paymentMethod}
              </span>
            </div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div className="rounded-xl border p-4">
            <div className="text-gray-600">Subtotal</div>
            <div className="font-semibold">{formatMoney(subtotal)}</div>
          </div>
          <div className="rounded-xl border p-4">
            <div className="text-gray-600">Tax</div>
            <div className="font-semibold">{formatMoney(tax)}</div>
          </div>
          <div className="rounded-xl border p-4">
            <div className="text-gray-600">Discount</div>
            <div className="font-semibold">{formatMoney(discount)}</div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border bg-white print-wrap">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="font-semibold">Payments</div>
          <div className="text-sm text-gray-600">
            {allocations.length ? `${allocations.length} leg(s)` : "Single"}
          </div>
        </div>

        {allocations.length === 0 ? (
          <div className="p-6 text-sm text-gray-600">
            Method:{" "}
            <span className="font-mono text-gray-800">{paymentMethod}</span>
          </div>
        ) : (
          <div className="p-4 space-y-3">
            {allocations.map((a, idx) => (
              <div
                key={a.id || `${a.method || "leg"}-${idx}`}
                className="border rounded-xl p-4 flex items-start justify-between gap-4 flex-wrap"
              >
                <div className="min-w-[220px]">
                  <div className="font-semibold text-gray-900">
                    {String(a.method || "—").toUpperCase()}
                  </div>

                  <div className="text-xs text-gray-500 mt-1 space-y-1">
                    {a.reference ? (
                      <div>
                        Ref: <span className="font-mono">{a.reference}</span>
                      </div>
                    ) : null}
                    {a.note ? <div>Note: {a.note}</div> : null}
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-sm text-gray-600">Amount</div>
                  <div className="font-semibold">
                    {formatMoney(toNumber(a.amount || 0))}
                  </div>
                </div>
              </div>
            ))}

            <div className="text-xs text-gray-500 pt-2">
              Allocations sum:{" "}
              <span className="font-mono text-gray-800">
                {formatMoney(paidLegsSum ?? 0)}
              </span>
              {paidLegsSum != null &&
              Math.round(paidLegsSum * 100) !== Math.round(total * 100) ? (
                <span className="ml-2 text-amber-700">
                  • Warning: allocations do not equal total
                </span>
              ) : null}
            </div>
          </div>
        )}
      </div>

      <div className="rounded-2xl border bg-white print-wrap">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="font-semibold">Items</div>
          <div className="text-sm text-gray-600">{items.length} line(s)</div>
        </div>

        {items.length === 0 ? (
          <div className="p-6 text-gray-600">
            Items are not included in this staff receipt response yet.
          </div>
        ) : (
          <div className="p-4 space-y-3">
            {items.map((it, idx) => {
              const name = it.product_name || it.name || "Item";
              const qty = toNumber(it.quantity || 0);
              const unit = toNumber(it.unit_price ?? it.unit_price_amount ?? 0);
              const line = toNumber(
                it.total_price ?? it.line_total ?? it.total_amount ?? unit * qty
              );

              return (
                <div
                  key={it.id || `${it.product_id || "line"}-${idx}`}
                  className="border rounded-xl p-4 flex items-start justify-between gap-4"
                >
                  <div className="min-w-0">
                    <div className="font-semibold text-gray-900 truncate">
                      {name}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      Qty: <span className="font-mono">{qty}</span>
                      <span className="mx-2 text-gray-300">•</span>
                      Unit:{" "}
                      <span className="font-mono">{formatMoney(unit)}</span>
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="text-sm text-gray-600">Line total</div>
                    <div className="font-semibold">{formatMoney(line)}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="no-print flex gap-2 flex-wrap">
        <Link
          to={`/pos/${storeId}`}
          className="px-4 py-2 rounded-md border hover:bg-gray-50"
        >
          New sale
        </Link>
        <Link
          to="/sales"
          className="px-4 py-2 rounded-md border hover:bg-gray-50"
        >
          Sales history
        </Link>
      </div>
    </div>
  );
}
