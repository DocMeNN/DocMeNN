// src/pages/ShopPage.jsx
/**
 * ======================================================
 * PUBLIC SHOP PAGE (ONLINE STORE, STORE-SCOPED)
 * ------------------------------------------------------
 * Route: /store/:storeId/shop
 *
 * Rules:
 * - storeId comes from URL (non-negotiable)
 * - backend is the source of truth for stock + pricing
 * - this page is AllowAny (public)
 *
 * Cart (V1):
 * - localStorage public cart per store
 * - does NOT touch staff POS cart endpoints
 * ======================================================
 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { fetchPublicProducts } from "../features/pos/pos.api";
import { formatMoney } from "../utils/money";
import { addToPublicCart, countPublicCartItems } from "../lib/publicCart";

export default function ShopPage() {
  const { storeId } = useParams();
  const navigate = useNavigate();

  const [q, setQ] = useState("");
  const [typing, setTyping] = useState("");
  const [products, setProducts] = useState([]);
  const [booting, setBooting] = useState(true);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState("");

  const cartCount = useMemo(() => {
    if (!storeId) return 0;
    return countPublicCartItems(storeId);
  }, [storeId, status]); // status changes after add-to-cart

  useEffect(() => {
    const t = setTimeout(() => setQ(String(typing || "").trim()), 350);
    return () => clearTimeout(t);
  }, [typing]);

  async function loadProducts(query) {
    if (!storeId) return;

    setLoading(true);
    setErr("");
    setStatus("");

    try {
      const list = await fetchPublicProducts({ storeId, q: query || "" });
      setProducts(Array.isArray(list) ? list : []);
    } catch (e) {
      setErr(e?.message || "Failed to load products.");
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    async function boot() {
      setBooting(true);
      setErr("");
      setStatus("");
      setProducts([]);

      if (!storeId) {
        setErr("Store not selected.");
        setBooting(false);
        return;
      }

      await loadProducts("");
      setBooting(false);
    }

    boot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeId]);

  useEffect(() => {
    if (!storeId) return;
    loadProducts(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  if (booting) {
    return <div className="p-6 text-gray-600">Loading shop…</div>;
  }

  if (!storeId) {
    return (
      <div className="rounded-2xl border bg-white p-6">
        <h1 className="text-xl font-semibold">Shop</h1>
        <p className="text-gray-600 mt-2">No store selected.</p>

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => navigate("/store")}
            className="px-4 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800"
          >
            Choose a Store
          </button>

          {/* ✅ safe escape hatch */}
          <button
            type="button"
            onClick={() => navigate("/")}
            className="px-4 py-2 rounded-md border hover:bg-gray-50"
          >
            Back to Home
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ✅ Breadcrumb + Quick Nav */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-sm text-gray-600">
          {/* Staff "home" */}
          <button
            type="button"
            onClick={() => navigate("/")}
            className="hover:underline"
          >
            Home
          </button>{" "}
          <span className="mx-2">/</span>
          {/* Public storefront "home" */}
          <button
            type="button"
            onClick={() => navigate("/store")}
            className="hover:underline"
          >
            Stores
          </button>{" "}
          <span className="mx-2">/</span>
          <span className="text-gray-900 font-medium">Shop</span>
        </div>

        <div className="flex gap-2">
          {/* ✅ Back to Store Picker */}
          <button
            type="button"
            onClick={() => navigate("/store")}
            className="px-3 py-2 rounded-md border hover:bg-gray-50"
          >
            Back to Stores
          </button>

          <button
            type="button"
            onClick={() => navigate(`/store/${storeId}/cart`)}
            className="px-4 py-2 rounded-md border hover:bg-gray-50"
          >
            Cart ({cartCount})
          </button>
        </div>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">Shop</h1>
          <p className="text-sm text-gray-600 mt-1">
            Browse products for this store. Stock shown is backend-truth.
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="flex flex-wrap items-center gap-3">
        <input
          className="border px-3 py-2 rounded w-full sm:w-96"
          placeholder="Search products (name / sku / barcode)…"
          value={typing}
          onChange={(e) => setTyping(e.target.value)}
          autoComplete="off"
        />

        <button
          type="button"
          onClick={() => loadProducts(q)}
          className="px-4 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800"
          disabled={loading}
        >
          {loading ? "Searching…" : "Search"}
        </button>

        <button
          type="button"
          onClick={() => {
            setTyping("");
            setQ("");
          }}
          className="px-4 py-2 rounded-md border hover:bg-gray-50"
          disabled={loading}
        >
          Clear
        </button>
      </div>

      {(err || status) && (
        <div
          className={`border rounded p-3 text-sm ${
            err
              ? "border-red-200 bg-red-50 text-red-800"
              : "border-green-200 bg-green-50 text-green-800"
          }`}
        >
          {err || status}
        </div>
      )}

      {/* Products */}
      <div className="rounded-2xl border bg-white">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="font-semibold">Products</div>
          <div className="text-sm text-gray-600">
            {loading ? "Loading…" : `${products.length} items`}
          </div>
        </div>

        {products.length === 0 ? (
          <div className="p-6 text-gray-600">
            {loading ? "Loading products…" : "No products found."}
          </div>
        ) : (
          <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {products.map((p) => {
              const out = Number(p.total_stock || 0) <= 0;

              return (
                <div
                  key={p.id}
                  className="border rounded-xl p-4 flex flex-col gap-2"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-gray-900">{p.name}</div>
                      <div className="text-sm text-gray-600">
                        {formatMoney(p.unit_price)}
                      </div>
                    </div>

                    <div
                      className={`text-xs px-2 py-1 rounded-full border ${
                        out
                          ? "bg-red-50 text-red-700 border-red-200"
                          : "bg-green-50 text-green-700 border-green-200"
                      }`}
                    >
                      {out ? "Out of stock" : `Stock: ${p.total_stock}`}
                    </div>
                  </div>

                  <div className="text-xs text-gray-500">
                    {p.sku ? (
                      <>
                        SKU: <span className="font-mono">{p.sku}</span>
                      </>
                    ) : (
                      " "
                    )}
                  </div>

                  <div className="pt-2 mt-auto flex gap-2">
                    <button
                      type="button"
                      disabled={out}
                      onClick={() => {
                        const next = addToPublicCart(storeId, p, 1);
                        const count = next.items.reduce(
                          (sum, it) => sum + Number(it.quantity || 0),
                          0
                        );
                        setStatus(`Added to cart • Items: ${count}`);
                      }}
                      className="flex-1 px-3 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
                    >
                      Add to cart
                    </button>

                    <button
                      type="button"
                      onClick={() => navigate(`/store/${storeId}/cart`)}
                      className="px-3 py-2 rounded-md border hover:bg-gray-50"
                    >
                      View
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="text-xs text-gray-500">
        V1 cart is local-only (public). POS cart remains staff-only.
      </div>
    </div>
  );
}
