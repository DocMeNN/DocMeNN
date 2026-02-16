/**
 * ======================================================
 * PATH: src/features/inventory/ExpiryAlertsPage.jsx
 * ======================================================
 *
 * EXPIRY ALERTS (UX) — PHASE 2 REMAINING ITEM
 * ------------------------------------------------------
 * Purpose:
 * - Display active stock batches expiring within N days.
 * - Store-scoped (multi-store safe).
 *
 * Store resolution (priority):
 * 1) Route/storeId prop (explicit)
 * 2) localStorage.active_store_id
 * 3) localStorage.store_id (legacy fallback)
 *
 * Listens to:
 * - window "active-store-changed" (from StoreSelector)
 *
 * Backend:
 * - GET /api/products/stock-batches/alerts/expiring-soon/?days=30&store_id=...
 *
 * Rules:
 * - Backend is source of truth.
 * - Only show batches with quantity_remaining > 0 (backend filters is_active).
 * ======================================================
 */

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchExpiringSoon } from "./inventory.api";

function resolveStoreId(explicitStoreId) {
  const s =
    String(explicitStoreId || "").trim() ||
    String(localStorage.getItem("active_store_id") || "").trim() ||
    String(localStorage.getItem("store_id") || "").trim();
  return s || null;
}

function formatDate(d) {
  if (!d) return "-";
  try {
    const dt = new Date(`${d}T00:00:00`);
    return dt.toLocaleDateString();
  } catch {
    return String(d);
  }
}

function daysLeft(expiryDate) {
  if (!expiryDate) return null;
  const today = new Date();
  const d0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const ex = new Date(`${expiryDate}T00:00:00`);
  if (Number.isNaN(ex.getTime())) return null;
  const diffMs = ex.getTime() - d0.getTime();
  return Math.floor(diffMs / (1000 * 60 * 60 * 24));
}

function getErrorMessage(err, fallback) {
  return (
    err?.response?.data?.detail ||
    err?.response?.data?.error?.message ||
    err?.message ||
    fallback
  );
}

function normalizeResults(data) {
  const raw = Array.isArray(data?.results)
    ? data.results
    : Array.isArray(data)
    ? data
    : [];

  return raw.map((b) => {
    const productName =
      b?.product_name ||
      b?.product?.name ||
      b?.product?.title ||
      b?.product?.product_name ||
      b?.name ||
      "Product";

    return {
      id: b.id,
      productName,
      batchNumber: b?.batch_number || "-",
      expiryDate: b?.expiry_date || null,
      qtyRemaining: Number(b?.quantity_remaining ?? 0) || 0,
      storeName: b?.store_name || b?.store?.name || "",
    };
  });
}

function severityBadgeClass(days) {
  if (days === null || days === undefined)
    return "bg-gray-100 text-gray-700 border-gray-200";
  if (days < 0) return "bg-red-50 text-red-700 border-red-200";
  if (days <= 7) return "bg-amber-50 text-amber-700 border-amber-200";
  if (days <= 30) return "bg-yellow-50 text-yellow-700 border-yellow-200";
  return "bg-gray-100 text-gray-700 border-gray-200";
}

function severityLabel(days) {
  if (days === null || days === undefined) return "Unknown";
  if (days < 0) return "Expired";
  if (days <= 7) return "Critical";
  if (days <= 30) return "Soon";
  return "OK";
}

function clampDays(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 30;
  return Math.max(0, Math.floor(n));
}

export default function ExpiryAlertsPage({ storeId }) {
  const [days, setDays] = useState(30);

  // ✅ Store is reactive: route param OR StoreSelector event/localStorage
  const [activeStoreId, setActiveStoreId] = useState(() => resolveStoreId(storeId));

  // If route param changes, it wins immediately
  useEffect(() => {
    setActiveStoreId(resolveStoreId(storeId));
  }, [storeId]);

  // Listen to StoreSelector broadcasts
  useEffect(() => {
    const handler = (evt) => {
      const sid = String(evt?.detail?.storeId || "").trim() || null;
      setActiveStoreId(sid);
    };
    window.addEventListener("active-store-changed", handler);

    // Also sync once on mount in case localStorage was set before component mounted
    setActiveStoreId(resolveStoreId(storeId));

    return () => window.removeEventListener("active-store-changed", handler);
  }, [storeId]);

  const query = useQuery({
    queryKey: ["inventory", "expiry-alerts", activeStoreId, days],
    queryFn: () => fetchExpiringSoon({ storeId: activeStoreId, days }),
    enabled: Boolean(activeStoreId),
    retry: 1,
    refetchOnWindowFocus: false,
  });

  const rows = useMemo(() => normalizeResults(query.data), [query.data]);

  const sorted = useMemo(() => {
    // Sort by days left asc, then expiry date
    return [...rows].sort((a, b) => {
      const da = daysLeft(a.expiryDate);
      const db = daysLeft(b.expiryDate);
      const na = da === null ? Number.POSITIVE_INFINITY : da;
      const nb = db === null ? Number.POSITIVE_INFINITY : db;
      if (na !== nb) return na - nb;
      return String(a.expiryDate || "").localeCompare(String(b.expiryDate || ""));
    });
  }, [rows]);

  const errorMessage = query.isError
    ? getErrorMessage(query.error, "Failed to load expiry alerts.")
    : null;

  const quickStats = useMemo(() => {
    const dls = sorted.map((r) => daysLeft(r.expiryDate)).filter((x) => x !== null);
    const expired = dls.filter((d) => d < 0).length;
    const critical = dls.filter((d) => d >= 0 && d <= 7).length;
    const soon = dls.filter((d) => d >= 8 && d <= 30).length;
    return { expired, critical, soon };
  }, [sorted]);

  return (
    <div className="space-y-4">
      <div className="bg-white border rounded-xl p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Expiry Alerts</h2>
            <p className="text-sm text-gray-500 mt-1">
              Active batches expiring within the selected window (store-scoped).
            </p>
            <p className="text-xs text-gray-500 mt-1">
              Active store:{" "}
              <span className="font-mono text-gray-800">
                {activeStoreId || "— not set —"}
              </span>
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-600">Days</label>
              <input
                type="number"
                min={0}
                value={days}
                onChange={(e) => setDays(clampDays(e.target.value))}
                className="w-24 px-3 py-2 border rounded-md text-sm"
              />
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setDays(7)}
                className="px-3 py-2 rounded-md border hover:bg-gray-50 text-sm"
              >
                7
              </button>
              <button
                type="button"
                onClick={() => setDays(30)}
                className="px-3 py-2 rounded-md border hover:bg-gray-50 text-sm"
              >
                30
              </button>
              <button
                type="button"
                onClick={() => setDays(90)}
                className="px-3 py-2 rounded-md border hover:bg-gray-50 text-sm"
              >
                90
              </button>
            </div>

            <button
              type="button"
              onClick={() => query.refetch()}
              className="px-3 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800 text-sm disabled:opacity-50"
              disabled={!activeStoreId || query.isFetching}
              title={!activeStoreId ? "Select a store to view expiry alerts" : "Refresh"}
            >
              {query.isFetching ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>

        {!activeStoreId ? (
          <div className="mt-4 rounded-lg border bg-amber-50 p-4 text-sm text-amber-800">
            <div className="font-medium">Store is required</div>
            <div className="mt-1">
              Expiry Alerts is store-scoped. Use the Store selector in the top bar
              to choose an active store, then return here.
            </div>
          </div>
        ) : null}

        {errorMessage ? (
          <div className="mt-4 rounded-lg border bg-red-50 p-4 text-sm text-red-800">
            {errorMessage}
          </div>
        ) : null}

        {activeStoreId && !query.isLoading && !errorMessage ? (
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <span className="inline-flex items-center px-2.5 py-1 rounded-full border bg-red-50 text-red-700 border-red-200">
              Expired: {quickStats.expired}
            </span>
            <span className="inline-flex items-center px-2.5 py-1 rounded-full border bg-amber-50 text-amber-700 border-amber-200">
              Critical (0–7): {quickStats.critical}
            </span>
            <span className="inline-flex items-center px-2.5 py-1 rounded-full border bg-yellow-50 text-yellow-700 border-yellow-200">
              Soon (8–30): {quickStats.soon}
            </span>
          </div>
        ) : null}
      </div>

      <div className="bg-white border rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b flex items-center justify-between">
          <div className="text-sm text-gray-600">
            {query.isLoading ? "Loading..." : `${sorted.length} result(s)`}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left font-medium px-5 py-3">Status</th>
                <th className="text-left font-medium px-5 py-3">Product</th>
                <th className="text-left font-medium px-5 py-3">Batch</th>
                <th className="text-left font-medium px-5 py-3">Expiry</th>
                <th className="text-right font-medium px-5 py-3">Days Left</th>
                <th className="text-right font-medium px-5 py-3">Qty Remaining</th>
              </tr>
            </thead>

            <tbody className="divide-y">
              {query.isLoading ? (
                <tr>
                  <td className="px-5 py-6 text-gray-500" colSpan={6}>
                    Loading expiry alerts…
                  </td>
                </tr>
              ) : !activeStoreId ? (
                <tr>
                  <td className="px-5 py-6 text-gray-500" colSpan={6}>
                    Select an active store to view expiry alerts.
                  </td>
                </tr>
              ) : sorted.length === 0 ? (
                <tr>
                  <td className="px-5 py-6 text-gray-500" colSpan={6}>
                    No active batches expiring within {days} day(s).
                  </td>
                </tr>
              ) : (
                sorted.map((r) => {
                  const dl = daysLeft(r.expiryDate);
                  const badgeClass = severityBadgeClass(dl);
                  return (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="px-5 py-3">
                        <span
                          className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs ${badgeClass}`}
                        >
                          {severityLabel(dl)}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-gray-900">{r.productName}</td>
                      <td className="px-5 py-3 text-gray-700">{r.batchNumber}</td>
                      <td className="px-5 py-3 text-gray-700">{formatDate(r.expiryDate)}</td>
                      <td className="px-5 py-3 text-right font-mono">
                        {dl === null ? "-" : dl}
                      </td>
                      <td className="px-5 py-3 text-right font-mono">{r.qtyRemaining}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
