// src/pages/InventoryPage.jsx

/**
 * ======================================================
 * PATH: src/pages/InventoryPage.jsx
 * ======================================================
 *
 * INVENTORY PAGE (STAFF)
 *
 * Fix:
 * - ✅ React Hooks order bug fixed (minified error #310 / "Rendered more hooks..."):
 *   All hooks are now called unconditionally before any conditional return.
 *
 * Upgrade (Category inline create):
 * - ✅ Add "New category" inline input + Create button inside Add Product modal
 * - ✅ Uses createCategory() API
 * - ✅ Refreshes categories + auto-selects newly created category
 * - ✅ Respects backend permissions (admin-only by default; shows error if forbidden)
 */

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import {
  fetchCategories,
  fetchProducts,
  createProduct,
  intakeStockBatch,
  resolveStoreId,
  createCategory,
} from "../features/pos/pos.api";

import { fetchExpiringSoon } from "../features/inventory/inventory.api";
import { formatMoney } from "../utils/money";

function formatOptionalMoney(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "—";
  return formatMoney(n);
}

function normalizeProducts(list) {
  const rawProducts = Array.isArray(list) ? list : [];

  return rawProducts.map((p) => {
    const price = p.unit_price ?? p.price ?? p.selling_price ?? p.cost_price ?? 0;

    const stock =
      p.total_stock ??
      p.stock ??
      p.quantity ??
      p.available_quantity ??
      p.available_stock ??
      0;

    const threshold = Number.isFinite(Number(p.low_stock_threshold))
      ? Number(p.low_stock_threshold)
      : null;

    const isLowStock =
      typeof p.is_low_stock === "boolean"
        ? p.is_low_stock
        : threshold === null
        ? false
        : Number(stock) <= Number(threshold);

    return {
      id: p.id,
      sku: (p.sku || "—").toString(),
      name: (p.name || p.product_name || "—").toString(),
      price: Number(price) || 0,
      stock: Number(stock) || 0,
      threshold,
      isLowStock,
      isActive: typeof p.is_active === "boolean" ? p.is_active : true,
      store: p.store ?? null,
      category: p.category ?? null,
      category_name: p.category_name ?? "",
    };
  });
}

function getErrorMessage(err, fallback) {
  return (
    err?.response?.data?.detail ||
    err?.response?.data?.error?.message ||
    err?.message ||
    fallback
  );
}

function Badge({ children, tone = "gray" }) {
  const toneClass =
    tone === "red"
      ? "bg-red-50 text-red-700 border-red-200"
      : tone === "green"
      ? "bg-green-50 text-green-700 border-green-200"
      : tone === "blue"
      ? "bg-blue-50 text-blue-700 border-blue-200"
      : tone === "amber"
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : "bg-gray-50 text-gray-700 border-gray-200";

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 text-xs font-medium border rounded ${toneClass}`}
    >
      {children}
    </span>
  );
}

function Toggle({ checked, onChange, label }) {
  return (
    <label className="inline-flex items-center gap-2 text-sm text-gray-700 select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4"
      />
      {label}
    </label>
  );
}

function SortSelect({ value, onChange }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-10 rounded-lg border bg-white px-3 text-sm"
    >
      <option value="name_asc">Name (A → Z)</option>
      <option value="name_desc">Name (Z → A)</option>
      <option value="stock_asc">Stock (Low → High)</option>
      <option value="stock_desc">Stock (High → Low)</option>
      <option value="price_asc">Price (Low → High)</option>
      <option value="price_desc">Price (High → Low)</option>
    </select>
  );
}

function sortProducts(items, sortKey) {
  const arr = [...items];
  const byStr = (a, b) => a.localeCompare(b, undefined, { sensitivity: "base" });
  const byNum = (a, b) => (a ?? 0) - (b ?? 0);

  switch (sortKey) {
    case "name_desc":
      return arr.sort((a, b) => byStr(b.name, a.name));
    case "stock_asc":
      return arr.sort((a, b) => byNum(a.stock, b.stock));
    case "stock_desc":
      return arr.sort((a, b) => byNum(b.stock, a.stock));
    case "price_asc":
      return arr.sort((a, b) => byNum(a.price, b.price));
    case "price_desc":
      return arr.sort((a, b) => byNum(b.price, a.price));
    case "name_asc":
    default:
      return arr.sort((a, b) => byStr(a.name, b.name));
  }
}

function Modal({ open, title, children, onClose }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <div className="w-full max-w-2xl rounded-xl bg-white shadow-lg border">
          <div className="flex items-center justify-between px-5 py-4 border-b">
            <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
            <button
              type="button"
              className="px-3 py-1 rounded border text-sm"
              onClick={onClose}
            >
              Close
            </button>
          </div>
          <div className="p-5">{children}</div>
        </div>
      </div>
    </div>
  );
}

function toNumberOrNull(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return n;
}

// -----------------------------
// Expiry helpers (UI only)
// -----------------------------
function daysLeft(expiryDate) {
  if (!expiryDate) return null;
  try {
    const today = new Date();
    const d0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const ex = new Date(`${expiryDate}T00:00:00`);
    const diffMs = ex.getTime() - d0.getTime();
    return Math.floor(diffMs / (1000 * 60 * 60 * 24));
  } catch {
    return null;
  }
}

function formatDate(d) {
  if (!d) return "—";
  try {
    const dt = new Date(`${d}T00:00:00`);
    return dt.toLocaleDateString();
  } catch {
    return String(d);
  }
}

function normalizeExpiring(data) {
  const raw = Array.isArray(data?.results)
    ? data.results
    : Array.isArray(data)
    ? data
    : [];

  return raw.map((b) => ({
    id: b.id,
    productName: b?.product?.name || b?.product_name || "Product",
    batchNumber: b?.batch_number || "—",
    expiryDate: b?.expiry_date || null,
    qtyRemaining: Number(b?.quantity_remaining ?? 0) || 0,
  }));
}

export default function InventoryPage() {
  const navigate = useNavigate();

  // IMPORTANT: store id must be reactive (store selector lives in layout)
  const [activeStoreId, setActiveStoreId] = useState(() => resolveStoreId());

  // Listen to "active-store-changed" broadcast from layout StoreSelector
  useEffect(() => {
    const handler = (evt) => {
      const storeId = String(evt?.detail?.storeId || "").trim() || null;
      setActiveStoreId(storeId);
    };

    window.addEventListener("active-store-changed", handler);

    // Also sync once on mount in case localStorage changed before page mounted
    setActiveStoreId(resolveStoreId());

    return () => window.removeEventListener("active-store-changed", handler);
  }, []);

  const [query, setQuery] = useState("");
  const [onlyLowStock, setOnlyLowStock] = useState(false);
  const [onlyActive, setOnlyActive] = useState(true);
  const [sortKey, setSortKey] = useState("name_asc");

  // Add Product UI state
  const [addOpen, setAddOpen] = useState(false);
  const [addErr, setAddErr] = useState("");
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({
    sku: "",
    name: "",
    unit_price: "",
    category: "",
    low_stock_threshold: "10",
    is_active: true,
  });

  // Category inline-create state
  const [catName, setCatName] = useState("");
  const [catSaving, setCatSaving] = useState(false);
  const [catErr, setCatErr] = useState("");

  // Stock Intake UI state
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [intakeErr, setIntakeErr] = useState("");
  const [intakeSaving, setIntakeSaving] = useState(false);
  const [intakeForm, setIntakeForm] = useState({
    product_id: "",
    quantity_received: "",
    unit_cost: "",
    expiry_date: "",
    batch_number: "",
  });

  const {
    data: productsData,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["inventory", "products", activeStoreId],
    queryFn: async () => {
      if (!activeStoreId) {
        throw new Error(
          "No active store selected. Set active_store_id to view inventory."
        );
      }
      return fetchProducts({ storeId: activeStoreId });
    },
    retry: 1,
    refetchOnWindowFocus: false,
    enabled: !!activeStoreId,
  });

  const {
    data: categoriesData,
    isLoading: categoriesLoading,
    isError: categoriesError,
    error: categoriesErrObj,
    refetch: refetchCategories,
  } = useQuery({
    queryKey: ["inventory", "categories"],
    queryFn: fetchCategories,
    retry: 1,
    refetchOnWindowFocus: false,
    enabled: addOpen,
  });

  // ✅ Expiry alerts summary (quick preview)
  const EXPIRY_DAYS = 30;

  const expiryQuery = useQuery({
    queryKey: ["inventory", "expiry-alerts-preview", activeStoreId, EXPIRY_DAYS],
    queryFn: () =>
      fetchExpiringSoon({ storeId: activeStoreId, days: EXPIRY_DAYS }),
    retry: 1,
    refetchOnWindowFocus: false,
    enabled: !!activeStoreId,
  });

  const categories = useMemo(() => {
    const raw = Array.isArray(categoriesData) ? categoriesData : [];
    return raw.map((c) => ({
      id: c.id,
      name: c.name ?? "—",
    }));
  }, [categoriesData]);

  const products = useMemo(
    () => normalizeProducts(productsData || []),
    [productsData]
  );

  const stats = useMemo(() => {
    const active = products.filter((p) => p.isActive);
    const low = active.filter((p) => p.isLowStock);
    return {
      total: products.length,
      active: active.length,
      lowStock: low.length,
      lowStockTop: [...low].sort((a, b) => a.stock - b.stock).slice(0, 6),
    };
  }, [products]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = products;

    if (onlyActive) list = list.filter((p) => p.isActive);
    if (onlyLowStock) list = list.filter((p) => p.isLowStock);

    if (q) {
      list = list.filter((p) => {
        const sku = (p.sku || "").toLowerCase();
        const name = (p.name || "").toLowerCase();
        return sku.includes(q) || name.includes(q);
      });
    }

    return sortProducts(list, sortKey);
  }, [products, query, onlyActive, onlyLowStock, sortKey]);

  // ✅ IMPORTANT: compute these with hooks BEFORE any conditional return
  const expRows = useMemo(
    () => normalizeExpiring(expiryQuery.data),
    [expiryQuery.data]
  );

  const expCount = expRows.length;

  const expTop = useMemo(() => {
    return [...expRows]
      .sort((a, b) => {
        const da = daysLeft(a.expiryDate);
        const db = daysLeft(b.expiryDate);
        const na = da === null ? Number.POSITIVE_INFINITY : da;
        const nb = db === null ? Number.POSITIVE_INFINITY : db;
        if (na !== nb) return na - nb;
        return String(a.expiryDate || "").localeCompare(String(b.expiryDate || ""));
      })
      .slice(0, 6);
  }, [expRows]);

  const openAdd = () => {
    setAddErr("");
    setCatErr("");
    setCatName("");
    setCatSaving(false);
    setForm({
      sku: "",
      name: "",
      unit_price: "",
      category: "",
      low_stock_threshold: "10",
      is_active: true,
    });
    setAddOpen(true);
  };

  const closeAdd = () => {
    if (saving || catSaving) return;
    setAddOpen(false);
    setAddErr("");
    setCatErr("");
    setCatName("");
  };

  const onChange = (patch) => setForm((prev) => ({ ...prev, ...patch }));

  const submitAdd = async () => {
    setAddErr("");

    if (!activeStoreId) {
      return setAddErr(
        "No active store selected. Please select a store first (active_store_id)."
      );
    }

    const sku = String(form.sku || "").trim().toUpperCase();
    const name = String(form.name || "").trim();
    const unit_price = String(form.unit_price || "").trim();
    const category = String(form.category || "").trim();
    const lowStock = toNumberOrNull(form.low_stock_threshold);

    if (!sku) return setAddErr("SKU is required.");
    if (!name) return setAddErr("Product name is required.");

    const priceNum = Number(unit_price);
    if (!Number.isFinite(priceNum) || priceNum <= 0) {
      return setAddErr("Unit price must be a number greater than zero.");
    }

    if (lowStock === null || lowStock < 0) {
      return setAddErr("Low stock threshold must be a non-negative number.");
    }

    const payload = {
      store: activeStoreId,
      sku,
      name,
      unit_price: String(priceNum.toFixed(2)),
      low_stock_threshold: Math.floor(lowStock),
      is_active: !!form.is_active,
      category: category || null,
    };

    try {
      setSaving(true);
      await createProduct(payload, { storeId: activeStoreId });
      setAddOpen(false);
      await refetch();
      expiryQuery.refetch?.();
    } catch (e) {
      setAddErr(e?.message || "Failed to create product.");
    } finally {
      setSaving(false);
    }
  };

  // -----------------------------
  // Category inline create (admin only by default)
  // -----------------------------
  const submitNewCategory = async () => {
    setCatErr("");
    const name = String(catName || "").trim();
    if (!name) return setCatErr("Enter a category name.");

    try {
      setCatSaving(true);
      const created = await createCategory({ name });

      // Refresh list, then select it
      await refetchCategories();
      const newId = created?.id ? String(created.id) : "";

      if (newId) {
        onChange({ category: newId });
      } else {
        // fallback: try to match by name after refetch
        const lower = name.toLowerCase();
        const match = categories.find((c) => String(c.name || "").toLowerCase() === lower);
        if (match?.id) onChange({ category: String(match.id) });
      }

      setCatName("");
    } catch (e) {
      setCatErr(e?.message || "Failed to create category.");
    } finally {
      setCatSaving(false);
    }
  };

  // -----------------------------
  // Stock Intake handlers
  // -----------------------------
  const openIntake = (presetProductId = "") => {
    setIntakeErr("");

    if (!activeStoreId) {
      setIntakeErr(
        "No active store selected. Please select a store first (active_store_id)."
      );
    }

    setIntakeForm({
      product_id: presetProductId || "",
      quantity_received: "",
      unit_cost: "",
      expiry_date: "",
      batch_number: "",
    });

    setIntakeOpen(true);
  };

  const closeIntake = () => {
    if (intakeSaving) return;
    setIntakeOpen(false);
    setIntakeErr("");
  };

  const onIntakeChange = (patch) =>
    setIntakeForm((prev) => ({ ...prev, ...patch }));

  const submitIntake = async () => {
    setIntakeErr("");

    if (!activeStoreId) {
      return setIntakeErr(
        "No active store selected. Please select a store first (active_store_id)."
      );
    }

    const product_id = String(intakeForm.product_id || "").trim();
    const qty = Number(intakeForm.quantity_received);
    const cost = Number(intakeForm.unit_cost);
    const expiry_date = String(intakeForm.expiry_date || "").trim();
    const batch_number = String(intakeForm.batch_number || "").trim();

    if (!product_id) return setIntakeErr("Select a product.");
    if (!Number.isFinite(qty) || qty <= 0)
      return setIntakeErr("Quantity received must be > 0.");
    if (!Number.isFinite(cost) || cost <= 0)
      return setIntakeErr("Unit cost must be > 0.");
    if (!expiry_date) return setIntakeErr("Expiry date is required.");

    try {
      setIntakeSaving(true);

      await intakeStockBatch({
        productId: product_id,
        quantity_received: Math.floor(qty),
        unit_cost: cost,
        expiry_date,
        batch_number: batch_number || undefined,
      });

      setIntakeOpen(false);
      await refetch();
      expiryQuery.refetch?.();
    } catch (e) {
      setIntakeErr(e?.message || "Failed to intake stock.");
    } finally {
      setIntakeSaving(false);
    }
  };

  // --------------------------------------
  // Render guards (NO hooks below this line)
  // --------------------------------------
  if (!activeStoreId) {
    return (
      <div className="rounded-lg border bg-white p-4">
        <p className="text-sm font-medium text-gray-800">
          No active store selected
        </p>
        <p className="text-sm text-gray-600 mt-1">
          Use the Store selector in the top bar to choose an active store.
        </p>
      </div>
    );
  }

  if (isLoading) return <p className="p-4">Loading inventory…</p>;

  if (isError) {
    const message = getErrorMessage(error, "Failed to load products.");
    return (
      <div className="rounded-lg border bg-white p-4">
        <p className="text-sm font-medium text-gray-800">
          Couldn’t load inventory
        </p>
        <p className="text-sm text-gray-600 mt-1">{message}</p>

        <button
          type="button"
          onClick={() => refetch()}
          className="mt-3 inline-flex items-center rounded-lg border px-3 py-2 text-sm hover:bg-gray-50"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Inventory</h1>
          <p className="text-sm text-gray-600 mt-1">
            Products, prices, and live stock from active (non-expired) batches.
          </p>
          <p className="text-xs text-gray-500 mt-1">
            Active store: <span className="font-semibold">{activeStoreId}</span>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={stats.lowStock > 0 ? "red" : "green"}>
            Low stock: {stats.lowStock}
          </Badge>
          <Badge tone={expCount > 0 ? "amber" : "green"}>
            Expiring ≤ {EXPIRY_DAYS}d: {expiryQuery.isLoading ? "…" : expCount}
          </Badge>
          <Badge tone="blue">Active: {stats.active}</Badge>
          <Badge tone="gray">Total: {stats.total}</Badge>

          <button
            type="button"
            onClick={() => refetch()}
            className="ml-1 inline-flex items-center rounded-lg border px-3 py-2 text-sm hover:bg-gray-50"
            disabled={isFetching}
            title="Refresh from server"
          >
            {isFetching ? "Refreshing…" : "Refresh"}
          </button>

          <button
            type="button"
            onClick={() => navigate("/inventory/expiry-alerts")}
            className="ml-1 inline-flex items-center rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
            title="View expiring batches (store-scoped)"
          >
            View Expiry Alerts
          </button>

          <button
            type="button"
            onClick={() => openIntake("")}
            className="ml-1 inline-flex items-center rounded-lg border px-4 py-2 text-sm hover:bg-gray-50"
            title="Add stock to a product (purchase-led intake)"
          >
            + Stock Intake
          </button>

          <button
            type="button"
            onClick={openAdd}
            className="ml-1 inline-flex items-center rounded-lg bg-gray-900 text-white px-4 py-2 text-sm hover:bg-gray-800"
          >
            + Add Product
          </button>
        </div>
      </div>

      {/* ✅ Expiry alerts preview panel */}
      <div className="rounded-xl border bg-white p-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <p className="text-sm font-semibold text-gray-900">Expiry Alerts</p>
            <p className="text-xs text-gray-600 mt-0.5">
              Active batches expiring within {EXPIRY_DAYS} day(s)
            </p>
          </div>

          <div className="flex items-center gap-2">
            {expiryQuery.isError ? (
              <Badge tone="red">Failed</Badge>
            ) : expCount > 0 ? (
              <Badge tone="amber">{expCount} batch(es)</Badge>
            ) : (
              <Badge tone="green">None</Badge>
            )}

            <button
              type="button"
              onClick={() => expiryQuery.refetch()}
              className="inline-flex items-center rounded-lg border px-3 py-2 text-xs hover:bg-gray-50"
              disabled={expiryQuery.isFetching}
              title="Refresh expiry preview"
            >
              {expiryQuery.isFetching ? "Refreshing…" : "Refresh"}
            </button>

            <button
              type="button"
              onClick={() => navigate("/inventory/expiry-alerts")}
              className="inline-flex items-center rounded-lg bg-gray-900 text-white px-3 py-2 text-xs hover:bg-gray-800"
            >
              Open
            </button>
          </div>
        </div>

        {expiryQuery.isError ? (
          <div className="mt-3 text-xs text-red-700">
            {getErrorMessage(
              expiryQuery.error,
              "Failed to load expiry alerts preview."
            )}
          </div>
        ) : expiryQuery.isLoading ? (
          <div className="mt-3 text-sm text-gray-600">Loading expiry alerts…</div>
        ) : expTop.length === 0 ? (
          <div className="mt-3 text-sm text-gray-600">
            No active batches expiring within {EXPIRY_DAYS} day(s).
          </div>
        ) : (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {expTop.map((b) => {
              const dl = daysLeft(b.expiryDate);
              const label =
                dl === null ? "Unknown" : dl < 0 ? "Expired" : `${dl} day(s)`;
              const tone = dl !== null && dl <= 7 ? "red" : "amber";

              return (
                <div key={b.id} className="rounded-lg border p-3 bg-amber-50/40">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="text-sm font-semibold text-gray-900">
                        {b.productName}
                      </div>
                      <div className="text-xs text-gray-600 mt-0.5">
                        Batch: {b.batchNumber}
                      </div>
                    </div>
                    <Badge tone={tone}>{label}</Badge>
                  </div>

                  <div className="mt-2 text-xs text-gray-700">
                    Expiry:{" "}
                    <span className="font-medium">{formatDate(b.expiryDate)}</span>
                  </div>
                  <div className="mt-1 text-xs text-gray-700">
                    Qty remaining:{" "}
                    <span className="font-medium">{b.qtyRemaining}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Low-stock panel */}
      {stats.lowStock > 0 && (
        <div className="rounded-xl border bg-white p-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-gray-900">
                Low Stock Attention
              </p>
              <p className="text-xs text-gray-600 mt-0.5">
                Top items with the lowest remaining stock (active products only)
              </p>
            </div>
            <Badge tone="red">{stats.lowStock} item(s)</Badge>
          </div>

          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {stats.lowStockTop.map((p) => (
              <div key={p.id} className="rounded-lg border p-3 bg-red-50/40">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-gray-900">
                      {p.name}
                    </div>
                    <div className="text-xs text-gray-600 mt-0.5">
                      SKU: {p.sku}
                    </div>
                  </div>
                  <Badge tone="red">Low</Badge>
                </div>

                <div className="mt-2 text-sm text-gray-800">
                  Stock: <span className="font-semibold">{p.stock}</span>
                  {p.threshold !== null ? (
                    <span className="text-gray-600"> / Thresh: {p.threshold}</span>
                  ) : null}
                </div>

                <div className="mt-3">
                  <button
                    type="button"
                    onClick={() => openIntake(p.id)}
                    className="inline-flex items-center rounded-lg border px-3 py-2 text-xs hover:bg-gray-50"
                  >
                    Intake
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="rounded-xl border bg-white p-4">
        <div className="flex flex-col md:flex-row md:items-center gap-3">
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Search (SKU or name)
            </label>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. PARACETAMOL or SKU123"
              className="h-10 w-full rounded-lg border px-3 text-sm"
            />
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <div className="mt-5 md:mt-0">
              <Toggle
                checked={onlyActive}
                onChange={setOnlyActive}
                label="Active only"
              />
            </div>
            <div className="mt-5 md:mt-0">
              <Toggle
                checked={onlyLowStock}
                onChange={setOnlyLowStock}
                label="Low stock only"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Sort
              </label>
              <SortSelect value={sortKey} onChange={setSortKey} />
            </div>
          </div>
        </div>

        <div className="mt-3 text-xs text-gray-600">
          Showing{" "}
          <span className="font-semibold text-gray-900">{filtered.length}</span>{" "}
          result(s)
        </div>
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <p className="text-gray-600">No matching products found</p>
      ) : (
        <div className="overflow-auto rounded-lg border bg-white">
          <table className="w-full border-collapse">
            <thead>
              <tr className="bg-gray-50">
                <th className="border-b p-2 text-left text-sm font-semibold text-gray-700">
                  SKU
                </th>
                <th className="border-b p-2 text-left text-sm font-semibold text-gray-700">
                  Name
                </th>
                <th className="border-b p-2 text-left text-sm font-semibold text-gray-700">
                  Price
                </th>
                <th className="border-b p-2 text-left text-sm font-semibold text-gray-700">
                  Stock
                </th>
                <th className="border-b p-2 text-left text-sm font-semibold text-gray-700">
                  Status
                </th>
                <th className="border-b p-2 text-left text-sm font-semibold text-gray-700">
                  Actions
                </th>
              </tr>
            </thead>

            <tbody>
              {filtered.map((product) => {
                const rowTint = product.isActive
                  ? product.isLowStock
                    ? "bg-red-50"
                    : "bg-white"
                  : "bg-gray-50 opacity-70";

                return (
                  <tr key={product.id} className={rowTint}>
                    <td className="border-b p-2 text-sm text-gray-700">
                      {product.sku}
                    </td>
                    <td className="border-b p-2">
                      <div className="font-medium text-gray-900">
                        {product.name}
                      </div>
                      {product.threshold !== null && (
                        <div className="text-xs text-gray-500">
                          Threshold: {product.threshold}
                        </div>
                      )}
                      {product.category_name ? (
                        <div className="text-xs text-gray-500">
                          Category: {product.category_name}
                        </div>
                      ) : null}
                    </td>
                    <td className="border-b p-2 text-sm text-gray-700">
                      {formatOptionalMoney(product.price)}
                    </td>
                    <td className="border-b p-2 text-sm text-gray-700">
                      {product.stock}
                    </td>
                    <td className="border-b p-2">
                      {!product.isActive ? (
                        <Badge tone="gray">Inactive</Badge>
                      ) : product.isLowStock ? (
                        <Badge tone="red">Low stock</Badge>
                      ) : (
                        <Badge tone="green">OK</Badge>
                      )}
                    </td>
                    <td className="border-b p-2">
                      <button
                        type="button"
                        onClick={() => openIntake(product.id)}
                        className="inline-flex items-center rounded-lg border px-3 py-2 text-xs hover:bg-gray-50"
                      >
                        Intake
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Add Product Modal */}
      <Modal
        open={addOpen}
        title="Add Product"
        onClose={() => {
          if (saving || catSaving) return;
          closeAdd();
        }}
      >
        <div className="space-y-4">
          <div className="text-xs text-gray-600">
            Store scope:{" "}
            <span className="font-semibold text-gray-900">{activeStoreId}</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                SKU
              </label>
              <input
                value={form.sku}
                onChange={(e) => onChange({ sku: e.target.value })}
                className="h-10 w-full rounded-lg border px-3 text-sm"
                placeholder="e.g. SKU-001"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Name
              </label>
              <input
                value={form.name}
                onChange={(e) => onChange({ name: e.target.value })}
                className="h-10 w-full rounded-lg border px-3 text-sm"
                placeholder="e.g. Paracetamol 500mg"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Unit Price
              </label>
              <input
                value={form.unit_price}
                onChange={(e) => onChange({ unit_price: e.target.value })}
                className="h-10 w-full rounded-lg border px-3 text-sm"
                inputMode="decimal"
                placeholder="e.g. 250.00"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Low Stock Threshold
              </label>
              <input
                value={form.low_stock_threshold}
                onChange={(e) => onChange({ low_stock_threshold: e.target.value })}
                className="h-10 w-full rounded-lg border px-3 text-sm"
                inputMode="numeric"
                placeholder="e.g. 10"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Category
              </label>

              <div className="flex gap-2">
                <select
                  value={form.category}
                  onChange={(e) => onChange({ category: e.target.value })}
                  className="h-10 w-full rounded-lg border bg-white px-3 text-sm"
                >
                  <option value="">— None —</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>

                <button
                  type="button"
                  className="h-10 rounded-lg border px-3 text-sm hover:bg-gray-50"
                  onClick={() => refetchCategories()}
                  disabled={categoriesLoading || catSaving}
                  title="Reload categories"
                >
                  {categoriesLoading ? "…" : "↻"}
                </button>
              </div>

              {/* Inline create */}
              <div className="mt-2 flex flex-col sm:flex-row gap-2">
                <input
                  value={catName}
                  onChange={(e) => setCatName(e.target.value)}
                  className="h-10 w-full rounded-lg border px-3 text-sm"
                  placeholder="New category name (admin only)"
                  disabled={catSaving}
                />

                <button
                  type="button"
                  className="h-10 rounded-lg bg-gray-900 text-white px-4 text-sm hover:bg-gray-800 disabled:opacity-50"
                  onClick={submitNewCategory}
                  disabled={catSaving || !String(catName || "").trim()}
                  title="Create category"
                >
                  {catSaving ? "Creating…" : "+ Add"}
                </button>
              </div>

              {catErr && (
                <div className="mt-2 text-xs text-red-700">{catErr}</div>
              )}

              {categoriesError && (
                <div className="mt-2 text-xs text-red-700">
                  {getErrorMessage(categoriesErrObj, "Failed to load categories.")}
                </div>
              )}

              <div className="mt-1 text-[11px] text-gray-500">
                Note: Creating categories may require admin permission. If you get 403,
                ask an admin to create it or enable allowed groups on the backend.
              </div>
            </div>

            <div className="md:col-span-2 flex items-center gap-2">
              <input
                id="is_active"
                type="checkbox"
                checked={!!form.is_active}
                onChange={(e) => onChange({ is_active: e.target.checked })}
              />
              <label htmlFor="is_active" className="text-sm text-gray-700">
                Active
              </label>
            </div>
          </div>

          {addErr && (
            <div className="border rounded p-3 text-sm border-red-200 bg-red-50 text-red-800">
              {addErr}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="px-4 py-2 rounded border hover:bg-gray-50 disabled:opacity-50"
              onClick={closeAdd}
              disabled={saving || catSaving}
            >
              Cancel
            </button>
            <button
              type="button"
              className="px-5 py-2 rounded bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
              onClick={submitAdd}
              disabled={saving || catSaving}
            >
              {saving ? "Saving…" : "Create Product"}
            </button>
          </div>

          <div className="text-xs text-gray-500">
            Note: product is created once. Stock is added via Stock Intake (batches).
          </div>
        </div>
      </Modal>

      {/* Stock Intake Modal */}
      <Modal
        open={intakeOpen}
        title="Stock Intake (Purchase Receipt)"
        onClose={() => {
          if (intakeSaving) return;
          closeIntake();
        }}
      >
        <div className="space-y-4">
          <div className="text-xs text-gray-600">
            Store scope:{" "}
            <span className="font-semibold text-gray-900">{activeStoreId}</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="md:col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Product
              </label>
              <select
                value={intakeForm.product_id}
                onChange={(e) => onIntakeChange({ product_id: e.target.value })}
                className="h-10 w-full rounded-lg border bg-white px-3 text-sm"
              >
                <option value="">— Select product —</option>
                {products
                  .slice()
                  .sort((a, b) => a.name.localeCompare(b.name))
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.sku})
                    </option>
                  ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Quantity Received
              </label>
              <input
                value={intakeForm.quantity_received}
                onChange={(e) =>
                  onIntakeChange({ quantity_received: e.target.value })
                }
                className="h-10 w-full rounded-lg border px-3 text-sm"
                inputMode="numeric"
                placeholder="e.g. 50"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Unit Cost
              </label>
              <input
                value={intakeForm.unit_cost}
                onChange={(e) => onIntakeChange({ unit_cost: e.target.value })}
                className="h-10 w-full rounded-lg border px-3 text-sm"
                inputMode="decimal"
                placeholder="e.g. 120.00"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Expiry Date
              </label>
              <input
                type="date"
                value={intakeForm.expiry_date}
                onChange={(e) => onIntakeChange({ expiry_date: e.target.value })}
                className="h-10 w-full rounded-lg border px-3 text-sm"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">
                Batch Number (optional)
              </label>
              <input
                value={intakeForm.batch_number}
                onChange={(e) => onIntakeChange({ batch_number: e.target.value })}
                className="h-10 w-full rounded-lg border px-3 text-sm"
                placeholder="Leave blank to auto-generate"
              />
            </div>
          </div>

          {intakeErr && (
            <div className="border rounded p-3 text-sm border-red-200 bg-red-50 text-red-800">
              {intakeErr}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              className="px-4 py-2 rounded border hover:bg-gray-50 disabled:opacity-50"
              onClick={closeIntake}
              disabled={intakeSaving}
            >
              Cancel
            </button>
            <button
              type="button"
              className="px-5 py-2 rounded bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
              onClick={submitIntake}
              disabled={intakeSaving}
            >
              {intakeSaving ? "Saving…" : "Save Intake"}
            </button>
          </div>

          <div className="text-xs text-gray-500">
            This creates a StockBatch + StockMovement(RECEIPT) atomically (audit-safe).
          </div>
        </div>
      </Modal>
    </div>
  );
}