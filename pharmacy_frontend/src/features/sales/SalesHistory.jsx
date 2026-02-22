// src/features/sales/SalesHistory.jsx

/**
 * ======================================================
 * PATH: src/features/sales/SalesHistory.jsx
 * ======================================================
 *
 * SALES HISTORY (STAFF) — FULL + PARTIAL REFUNDS
 *
 * Golden Rule:
 * - You paste → I return a complete, final file for copy & replace.
 *
 * What this UI supports:
 * - FULL refund: omit items (backend processes full reversal)
 * - PARTIAL refund: send items=[{sale_item_id, quantity}, ...]
 *
 * Refund visibility:
 * - FULL refunds usually show via sale.refund_audit and/or status containing "refund".
 * - PARTIAL refunds may NOT change sale.status (backend-safe) — so we display them via:
 *     sale.is_partially_refunded
 *     sale.partial_refund_count
 *     sale.partial_refund_amount_total
 *     sale.partial_refund_last_at
 *     sale.refunded_amount_total
 *
 * Notes:
 * - Sales list may not include items. For partial refund UX, we fetch sale details on-demand.
 * - UI validates strongly, but backend enforces ceilings and rejects invalid payloads.
 *
 * Receipt rule:
 * - Staff receipt route is store-scoped:
 *   /pos/:storeId/receipt/:saleId
 * - We MUST have a storeId. We resolve it from:
 *   sale.store_id -> sale.store -> active_store_id
 * ======================================================
 */

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";

import { fetchSales, fetchSaleById, refundSale } from "./sales.api";
import { useAuth } from "../../context/AuthContext";
import { formatMoney } from "../../utils/money";

function resolveActiveStoreId() {
  return String(localStorage.getItem("active_store_id") || "").trim() || null;
}

function normalizeSales(data) {
  if (Array.isArray(data)) return data;
  if (data && typeof data === "object" && Array.isArray(data.results)) return data.results;
  return [];
}

function safeArray(v) {
  return Array.isArray(v) ? v : [];
}

function getSaleId(sale) {
  return sale?.id || sale?.sale_id || sale?.saleId || null;
}

function getInvoiceNo(sale) {
  return sale?.invoice_no || sale?.invoice || sale?.reference || "—";
}

function getSaleDateLabel(sale) {
  const raw = sale?.created_at || sale?.created || sale?.createdAt || null;
  if (!raw) return "—";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

function getSaleTotals(sale) {
  return {
    subtotal: Number(sale?.subtotal_amount ?? sale?.subtotal ?? 0) || 0,
    tax: Number(sale?.tax_amount ?? sale?.tax ?? 0) || 0,
    discount: Number(sale?.discount_amount ?? sale?.discount ?? 0) || 0,
    total: Number(sale?.total_amount ?? sale?.total ?? 0) || 0,
  };
}

function statusTone(status) {
  const s = String(status || "").toLowerCase();
  if (s.includes("refunded") || s.includes("reversed"))
    return "bg-amber-50 text-amber-800 border-amber-200";
  if (s.includes("partial")) return "bg-orange-50 text-orange-800 border-orange-200";
  if (s.includes("paid") || s.includes("completed") || s.includes("success"))
    return "bg-green-50 text-green-800 border-green-200";
  if (s.includes("void") || s.includes("cancel"))
    return "bg-gray-50 text-gray-700 border-gray-200";
  return "bg-blue-50 text-blue-800 border-blue-200";
}

function toInt(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.trunc(n));
}

function toNum(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return n;
}

// Best-effort: different serializers may expose refunded qty differently.
function getAlreadyRefundedQty(item) {
  return (
    toInt(item?.already_refunded_qty) ||
    toInt(item?.refunded_qty) ||
    toInt(item?.refunded_quantity) ||
    toInt(item?.quantity_refunded_total) ||
    0
  );
}

function hasFullRefund(sale) {
  const status = String(sale?.status || "").toLowerCase();
  if (status.includes("refunded") || status.includes("reversed")) return true;
  if (sale?.refund_audit) return true;
  return false;
}

function hasPartialRefund(sale) {
  if (hasFullRefund(sale)) return false;
  if (Boolean(sale?.is_partially_refunded)) return true;
  if (toInt(sale?.partial_refund_count) > 0) return true;
  if (toNum(sale?.partial_refund_amount_total) > 0) return true;
  return false;
}

function resolveSaleStoreId(sale, fallbackStoreId) {
  const sid =
    String(sale?.store_id || "").trim() ||
    String(sale?.store || "").trim() ||
    String(fallbackStoreId || "").trim();

  return sid || null;
}

function extractErrMessage(err, fallback = "Request failed.") {
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

  if (!data) return status ? `[${status}] ${err?.message || fallback}` : err?.message || fallback;
  if (typeof data === "string") return status ? `[${status}] ${data}` : data;

  return status ? `[${status}] ${fallback}` : fallback;
}

export default function SalesHistory() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [expandedSaleId, setExpandedSaleId] = useState(null);

  // Refund modal state
  const [refundSaleId, setRefundSaleId] = useState(null);
  const [refundReason, setRefundReason] = useState("");
  const [refundMode, setRefundMode] = useState("full"); // "full" | "partial"
  const [refundQtyByItemId, setRefundQtyByItemId] = useState({});

  // Lightweight notices (avoid alert spam)
  const [notice, setNotice] = useState({ type: "", message: "" });

  // Filters
  const [q, setQ] = useState("");
  const [onlyRefunded, setOnlyRefunded] = useState(false);

  const activeStoreId = resolveActiveStoreId();

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["sales", activeStoreId || "no-store"],
    queryFn: async () => fetchSales({ storeId: activeStoreId }),
    staleTime: 1000 * 30,
    retry: 1,
    refetchOnWindowFocus: false,
  });

  // Refetch when layout broadcasts active store change
  useEffect(() => {
    function onStoreChanged() {
      setNotice({ type: "", message: "" });
      setExpandedSaleId(null);
      closeRefundModal();
      refetch();
    }
    window.addEventListener("active-store-changed", onStoreChanged);
    return () => window.removeEventListener("active-store-changed", onStoreChanged);
  }, [refetch]);

  const sales = useMemo(() => normalizeSales(data), [data]);

  const filteredSales = useMemo(() => {
    const needle = String(q || "").trim().toLowerCase();
    let list = sales;

    if (onlyRefunded) {
      list = list.filter((s) => hasFullRefund(s) || hasPartialRefund(s));
    }

    if (needle) {
      list = list.filter((s) => {
        const inv = String(getInvoiceNo(s)).toLowerCase();
        const pm = String(s?.payment_method || "").toLowerCase();
        const status = String(s?.status || "").toLowerCase();
        return inv.includes(needle) || pm.includes(needle) || status.includes(needle);
      });
    }

    return [...list].sort((a, b) => {
      const da = new Date(a?.created_at || a?.created || 0).getTime() || 0;
      const db = new Date(b?.created_at || b?.created || 0).getTime() || 0;
      return db - da;
    });
  }, [sales, q, onlyRefunded]);

  const canRefund = user?.role === "admin" || user?.role === "pharmacist";

  // On-demand: sale detail for refund modal (items etc)
  const refundSaleDetailQuery = useQuery({
    queryKey: ["sale-detail", refundSaleId || "none"],
    queryFn: async () => fetchSaleById(refundSaleId),
    enabled: Boolean(refundSaleId),
    retry: 1,
    refetchOnWindowFocus: false,
    staleTime: 0,
  });

  const refundMutation = useMutation({
    mutationFn: ({ saleId, payload }) => refundSale(saleId, payload),
    onSuccess: (res) => {
      const ref = res?.refund_no || res?.refundNo || res?.reference || "—";
      const mode = res?.mode || (refundMode === "partial" ? "partial" : "full");

      setNotice({
        type: "success",
        message: `Refund successful (${mode}) • Refund No: ${ref}`,
      });

      queryClient.invalidateQueries({ queryKey: ["sales"] });
      if (refundSaleId) queryClient.invalidateQueries({ queryKey: ["sale-detail", refundSaleId] });

      closeRefundModal();
    },
    onError: (err) => {
      setNotice({
        type: "error",
        message: extractErrMessage(err, "Refund failed. Please try again."),
      });
    },
  });

  const openRefundModal = (sale) => {
    setNotice({ type: "", message: "" });

    const sid = getSaleId(sale);
    if (!sid) {
      setNotice({ type: "error", message: "Cannot refund: sale id missing." });
      return;
    }

    // If already fully refunded, do not allow
    if (hasFullRefund(sale)) {
      setNotice({ type: "error", message: "This sale is already fully refunded." });
      return;
    }

    setRefundSaleId(sid);
    setRefundReason("");
    setRefundMode("full");
    setRefundQtyByItemId({});
  };

  const closeRefundModal = () => {
    setRefundSaleId(null);
    setRefundReason("");
    setRefundMode("full");
    setRefundQtyByItemId({});
  };

  const refundSaleDetail = refundSaleDetailQuery.data || null;
  const refundItems = safeArray(refundSaleDetail?.items);
  const refundTotals = refundSaleDetail ? getSaleTotals(refundSaleDetail) : { total: 0 };

  const normalizedRefundLines = useMemo(() => {
    const lines = [];
    for (const item of refundItems) {
      const id = String(item?.id || "");
      if (!id) continue;

      const soldQty = toInt(item?.quantity);
      const already = getAlreadyRefundedQty(item);
      const remaining = Math.max(0, soldQty - already);

      const raw = refundQtyByItemId[id];
      const qty = toInt(raw);

      if (qty <= 0) continue;
      if (qty > remaining) continue;

      lines.push({ sale_item_id: id, quantity: qty });
    }
    return lines;
  }, [refundItems, refundQtyByItemId]);

  const partialValidation = useMemo(() => {
    if (refundMode !== "partial") return { ok: true, message: "" };

    if (!refundItems.length) {
      return { ok: false, message: "Sale items are not available yet. Cannot do partial refund." };
    }

    if (normalizedRefundLines.length === 0) {
      return { ok: false, message: "Select at least one item quantity to refund." };
    }

    for (const item of refundItems) {
      const id = String(item?.id || "");
      if (!id) continue;

      const soldQty = toInt(item?.quantity);
      const already = getAlreadyRefundedQty(item);
      const remaining = Math.max(0, soldQty - already);

      const raw = refundQtyByItemId[id];
      if (raw === undefined || raw === "" || raw === null) continue;

      const qty = toInt(raw);
      if (qty <= 0) continue;

      if (qty > remaining) {
        const name = item?.product_name || item?.name || "Item";
        return {
          ok: false,
          message: `${name}: cannot refund more than remaining qty (${remaining}).`,
        };
      }
    }

    return { ok: true, message: "" };
  }, [refundMode, refundItems, refundQtyByItemId, normalizedRefundLines]);

  const handleRefundSubmit = () => {
    if (!refundSaleId) return;

    const reason = String(refundReason || "").trim();

    if (refundMode === "partial") {
      if (!partialValidation.ok) {
        setNotice({
          type: "error",
          message: partialValidation.message || "Invalid partial refund.",
        });
        return;
      }

      refundMutation.mutate({
        saleId: refundSaleId,
        payload: {
          reason,
          items: normalizedRefundLines,
        },
      });
      return;
    }

    // FULL refund: omit items entirely
    refundMutation.mutate({
      saleId: refundSaleId,
      payload: { reason },
    });
  };

  if (isLoading) return <p className="p-6">Loading sales history…</p>;

  if (isError) {
    const msg = extractErrMessage(error, "Failed to load sales history.");
    return (
      <div className="p-6">
        <div className="rounded-xl border bg-white p-4">
          <div className="font-semibold text-gray-900">Sales History</div>
          <div className="mt-2 text-sm text-red-700">{msg}</div>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-3 inline-flex items-center rounded-lg border px-3 py-2 text-sm hover:bg-gray-50"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">Sales History</h1>
          <p className="text-sm text-gray-600 mt-1">
            Logged in as: <span className="font-medium">{user?.username || "—"}</span>{" "}
            <span className="text-gray-400">({user?.role || "—"})</span>
          </p>
          <p className="text-xs text-gray-500 mt-1">
            Active store:{" "}
            <span className="font-mono font-semibold">{activeStoreId || "— not set —"}</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => refetch()}
            className="inline-flex items-center rounded-lg border px-3 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
            disabled={isFetching}
            title="Refresh from server"
          >
            {isFetching ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {/* Notice */}
      {notice?.message ? (
        <div
          className={`border rounded p-3 text-sm ${
            notice.type === "error"
              ? "border-red-200 bg-red-50 text-red-800"
              : "border-green-200 bg-green-50 text-green-800"
          }`}
        >
          {notice.message}
        </div>
      ) : null}

      {/* Filters */}
      <div className="rounded-xl border bg-white p-4 flex flex-col md:flex-row md:items-center gap-3">
        <div className="flex-1">
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Search (invoice / payment / status)
          </label>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. INV-00012, cash, split, refunded..."
            className="h-10 w-full rounded-lg border px-3 text-sm"
          />
        </div>

        <label className="inline-flex items-center gap-2 text-sm text-gray-700 select-none mt-6 md:mt-0">
          <input
            type="checkbox"
            checked={onlyRefunded}
            onChange={(e) => setOnlyRefunded(e.target.checked)}
            className="h-4 w-4"
          />
          Refunded only
        </label>

        <div className="text-xs text-gray-500 mt-2 md:mt-6">
          Showing <span className="font-semibold text-gray-900">{filteredSales.length}</span>{" "}
          sale(s)
        </div>
      </div>

      {/* Empty */}
      {filteredSales.length === 0 ? (
        <p className="text-gray-500">No sales recorded.</p>
      ) : (
        <div className="space-y-4">
          {filteredSales.map((sale) => {
            const saleId = getSaleId(sale);
            const invoiceNo = getInvoiceNo(sale);
            const isExpanded = expandedSaleId === saleId;

            const items = safeArray(sale?.items);
            const totals = getSaleTotals(sale);

            const pm = String(sale?.payment_method || "—");
            const status = String(sale?.status || "—");

            const receiptStoreId = resolveSaleStoreId(sale, activeStoreId);
            const receiptHref = saleId && receiptStoreId ? `/pos/${receiptStoreId}/receipt/${saleId}` : null;

            const isFullRefund = hasFullRefund(sale);
            const isPartial = hasPartialRefund(sale);

            const partialAmount = toNum(sale?.partial_refund_amount_total);
            const partialCount = toInt(sale?.partial_refund_count);

            return (
              <div key={saleId || invoiceNo} className="border rounded-2xl p-4 bg-white shadow-sm">
                <div className="flex justify-between items-start gap-4 flex-wrap">
                  <div>
                    <p className="font-semibold text-gray-900">Invoice #{invoiceNo}</p>
                    <p className="text-sm text-gray-500">{getSaleDateLabel(sale)}</p>

                    <div className="mt-2 flex items-center gap-2 flex-wrap">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 text-xs font-medium border rounded ${statusTone(
                          status
                        )}`}
                      >
                        {status}
                      </span>

                      <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium border rounded bg-gray-50 text-gray-700 border-gray-200">
                        {pm}
                      </span>

                      {sale?.refund_no ? (
                        <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium border rounded bg-amber-50 text-amber-800 border-amber-200">
                          Refund: {sale.refund_no}
                        </span>
                      ) : null}

                      {isFullRefund && !sale?.refund_no ? (
                        <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium border rounded bg-amber-50 text-amber-800 border-amber-200">
                          Full refund
                        </span>
                      ) : null}

                      {isPartial ? (
                        <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium border rounded bg-orange-50 text-orange-800 border-orange-200">
                          Partial refund
                          {partialCount ? ` ×${partialCount}` : ""}
                          {partialAmount ? ` • ${formatMoney(partialAmount)}` : ""}
                        </span>
                      ) : null}

                      {!receiptStoreId ? (
                        <span className="inline-flex items-center px-2 py-0.5 text-xs font-medium border rounded bg-red-50 text-red-800 border-red-200">
                          Store missing
                        </span>
                      ) : null}
                    </div>
                  </div>

                  <div className="text-right space-y-1">
                    <p className="font-bold text-lg">{formatMoney(totals.total)}</p>
                    <button
                      type="button"
                      onClick={() => setExpandedSaleId(isExpanded ? null : saleId)}
                      className="text-xs text-blue-600 underline"
                    >
                      {isExpanded ? "Hide details" : "View details"}
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <>
                    {/* Actions */}
                    <div className="mt-4 flex justify-end gap-2 flex-wrap">
                      {receiptHref ? (
                        <>
                          <Link to={receiptHref} className="text-sm px-3 py-2 rounded-lg border hover:bg-gray-50">
                            View Receipt
                          </Link>

                          <button
                            type="button"
                            onClick={() => navigate(receiptHref)}
                            className="text-sm px-3 py-2 rounded-lg border hover:bg-gray-50"
                            title="Open receipt (print is on receipt page)"
                          >
                            Print
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          disabled
                          className="text-sm px-3 py-2 rounded-lg border opacity-50"
                          title="Missing storeId or saleId"
                        >
                          View Receipt
                        </button>
                      )}

                      <button
                        type="button"
                        disabled={!canRefund || isFullRefund}
                        onClick={() => openRefundModal(sale)}
                        className={`text-sm px-3 py-2 rounded-lg border ${
                          canRefund && !isFullRefund ? "hover:bg-red-50" : "opacity-50 cursor-not-allowed"
                        }`}
                        title={
                          !canRefund
                            ? "Only admin/pharmacist can refund"
                            : isFullRefund
                            ? "Already fully refunded"
                            : "Refund (full or partial)"
                        }
                      >
                        Refund
                      </button>
                    </div>

                    {/* Items */}
                    <div className="mt-4">
                      {items.length === 0 ? (
                        <div className="text-sm text-gray-600">Items are not included in this sales response yet.</div>
                      ) : (
                        <div className="w-full overflow-x-auto">
                          <table className="min-w-[720px] w-full text-sm border-t">
                            <thead>
                              <tr className="text-left text-gray-600">
                                <th className="py-2">Product</th>
                                <th>Qty</th>
                                <th>Unit</th>
                                <th className="text-right">Total</th>
                              </tr>
                            </thead>
                            <tbody>
                              {items.map((item) => (
                                <tr key={item.id || `${item.product_id}-${item.quantity}`} className="border-t">
                                  <td className="py-2">{item.product_name || item.name || "—"}</td>
                                  <td>{Number(item.quantity || 0)}</td>
                                  <td>{formatMoney(Number(item.unit_price || 0))}</td>
                                  <td className="text-right">
                                    {formatMoney(Number(item.line_total ?? item.total_price ?? 0))}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>

                    {/* Totals */}
                    <div className="mt-4 text-sm text-right space-y-1">
                      <p>Subtotal: {formatMoney(totals.subtotal)}</p>
                      <p>Tax: {formatMoney(totals.tax)}</p>
                      <p>Discount: {formatMoney(totals.discount)}</p>
                      <p className="font-semibold">Grand Total: {formatMoney(totals.total)}</p>

                      {isPartial ? (
                        <p className="text-orange-700 font-medium">
                          Refunded so far: {formatMoney(toNum(sale?.refunded_amount_total) || partialAmount || 0)}
                        </p>
                      ) : null}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* REFUND MODAL (FULL or PARTIAL) */}
      {refundSaleId ? (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          {/* Shell: fixed height, no overflow. Body scrolls. Footer sticky. */}
          <div className="bg-white rounded-2xl w-full max-w-3xl max-h-[88vh] border shadow-lg overflow-hidden flex flex-col">
            {/* Header */}
            <div className="p-5 border-b bg-white">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold">Refund</h2>
                  <p className="text-sm text-gray-600 mt-1">
                    Invoice:{" "}
                    <span className="font-mono">
                      {refundSaleDetail ? getInvoiceNo(refundSaleDetail) : "Loading…"}
                    </span>
                  </p>
                </div>

                <button
                  type="button"
                  onClick={closeRefundModal}
                  className="px-3 py-1 rounded border text-sm hover:bg-gray-50"
                  disabled={refundMutation.isPending}
                >
                  Close
                </button>
              </div>

              {/* Mode toggle */}
              <div className="flex items-center gap-2 flex-wrap mt-4">
                <button
                  type="button"
                  onClick={() => setRefundMode("full")}
                  className={`px-3 py-2 rounded-lg border text-sm ${
                    refundMode === "full" ? "bg-gray-900 text-white border-gray-900" : "hover:bg-gray-50"
                  }`}
                  disabled={refundMutation.isPending}
                >
                  Full
                </button>
                <button
                  type="button"
                  onClick={() => setRefundMode("partial")}
                  className={`px-3 py-2 rounded-lg border text-sm ${
                    refundMode === "partial" ? "bg-gray-900 text-white border-gray-900" : "hover:bg-gray-50"
                  }`}
                  disabled={refundMutation.isPending}
                >
                  Partial
                </button>

                <div className="text-xs text-gray-500 ml-auto">
                  Backend enforces ceilings + accounting correctness.
                </div>
              </div>
            </div>

            {/* Scrollable Body */}
            <div className="p-5 space-y-4 overflow-y-auto">
              {/* Sale detail loading/errors */}
              {refundSaleDetailQuery.isLoading ? (
                <div className="rounded-xl border bg-white p-4 text-sm text-gray-700">
                  Loading sale details for refund…
                </div>
              ) : refundSaleDetailQuery.isError ? (
                <div className="rounded-xl border bg-red-50 p-4 text-sm text-red-800">
                  Failed to load sale details. Try closing and reopening the refund modal.
                </div>
              ) : null}

              {/* Full refund box */}
              {refundMode === "full" ? (
                <div className="rounded-xl border bg-amber-50/40 p-4 text-sm text-amber-900">
                  <div className="font-semibold">Full refund</div>
                  <div className="mt-1">This will refund the entire sale and reverse stock + ledger postings.</div>
                  <div className="mt-2">
                    Refund amount: <span className="font-semibold">{formatMoney(refundTotals.total || 0)}</span>
                  </div>
                </div>
              ) : (
                <div className="rounded-xl border bg-blue-50/40 p-4 text-sm text-blue-900">
                  <div className="font-semibold">Partial refund</div>
                  <div className="mt-1">
                    Select item quantities to refund. Backend will restore stock for those quantities and post a
                    proportional ledger reversal.
                  </div>
                </div>
              )}

              {/* Partial item picker */}
              {refundMode === "partial" ? (
                <div className="rounded-xl border p-4">
                  {!refundItems.length ? (
                    <div className="text-sm text-gray-700">
                      No items available on this sale detail response. Partial refund needs items.
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="text-sm font-semibold text-gray-900">Refund items</div>

                        <button
                          type="button"
                          className="text-xs px-3 py-2 rounded-lg border hover:bg-gray-50"
                          disabled={refundMutation.isPending}
                          onClick={() => {
                            const next = {};
                            for (const item of refundItems) {
                              const id = String(item?.id || "");
                              if (!id) continue;
                              const sold = toInt(item?.quantity);
                              const already = getAlreadyRefundedQty(item);
                              const remaining = Math.max(0, sold - already);
                              if (remaining > 0) next[id] = String(remaining);
                            }
                            setRefundQtyByItemId(next);
                          }}
                        >
                          Auto-fill remaining
                        </button>
                      </div>

                      <div className="w-full overflow-x-auto">
                        <table className="min-w-[860px] w-full text-sm border-t">
                          <thead>
                            <tr className="text-left text-gray-600">
                              <th className="py-2">Product</th>
                              <th className="w-20">Sold</th>
                              <th className="w-24">Refunded</th>
                              <th className="w-24">Remaining</th>
                              <th className="w-40 text-right">Refund qty</th>
                            </tr>
                          </thead>
                          <tbody>
                            {refundItems.map((item) => {
                              const id = String(item?.id || "");
                              const name = item?.product_name || item?.name || "—";
                              const sold = toInt(item?.quantity);
                              const already = getAlreadyRefundedQty(item);
                              const remaining = Math.max(0, sold - already);

                              const value = refundQtyByItemId[id] ?? "";

                              return (
                                <tr key={id} className="border-t">
                                  <td className="py-2">{name}</td>
                                  <td>{sold}</td>
                                  <td>{already}</td>
                                  <td className={remaining === 0 ? "text-red-600 font-semibold" : ""}>{remaining}</td>
                                  <td className="text-right">
                                    <div className="flex items-center justify-end gap-2">
                                      <input
                                        value={value}
                                        onChange={(e) => {
                                          const v = e.target.value;
                                          setRefundQtyByItemId((prev) => ({ ...prev, [id]: v }));
                                        }}
                                        inputMode="numeric"
                                        placeholder="0"
                                        className="h-9 w-20 rounded border px-2 text-right"
                                        disabled={refundMutation.isPending || remaining === 0}
                                        title={remaining === 0 ? "No refundable qty remaining" : ""}
                                      />
                                      <button
                                        type="button"
                                        className="text-xs px-2 py-2 rounded border hover:bg-gray-50"
                                        disabled={refundMutation.isPending || remaining === 0}
                                        title="Set to remaining"
                                        onClick={() =>
                                          setRefundQtyByItemId((prev) => ({ ...prev, [id]: String(remaining) }))
                                        }
                                      >
                                        Max
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>

                      {!partialValidation.ok && partialValidation.message ? (
                        <div className="mt-2 text-xs border rounded p-2 border-red-200 bg-red-50 text-red-800">
                          {partialValidation.message}
                        </div>
                      ) : (
                        <div className="mt-2 text-xs text-gray-500">
                          Tip: keep refund qty within the “Remaining” column.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : null}

              <textarea
                placeholder="Refund reason (optional)"
                value={refundReason}
                onChange={(e) => setRefundReason(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm"
                rows={3}
                disabled={refundMutation.isPending}
              />

              {notice.type === "error" && notice.message ? (
                <div className="border rounded p-3 text-sm border-red-200 bg-red-50 text-red-800">
                  {notice.message}
                </div>
              ) : null}
            </div>

            {/* Sticky Footer */}
            <div className="p-5 border-t bg-white sticky bottom-0">
              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={closeRefundModal}
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                  disabled={refundMutation.isPending}
                >
                  Cancel
                </button>

                <button
                  type="button"
                  onClick={handleRefundSubmit}
                  disabled={
                    refundMutation.isPending ||
                    !canRefund ||
                    (refundMode === "partial" && !partialValidation.ok)
                  }
                  className="px-4 py-2 bg-red-600 text-white rounded-lg disabled:opacity-50"
                  title={!canRefund ? "Only admin/pharmacist can refund" : "Confirm refund"}
                >
                  {refundMutation.isPending
                    ? "Refunding…"
                    : refundMode === "partial"
                    ? "Confirm Partial Refund"
                    : "Confirm Full Refund"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}