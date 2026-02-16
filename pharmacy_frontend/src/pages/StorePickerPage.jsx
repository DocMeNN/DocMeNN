// src/pages/StorePickerPage.jsx

/**
 * ======================================================
 * ONLINE STORE ENTRY (PUBLIC)
 * ------------------------------------------------------
 * Route: /store
 *
 * - Loads stores from PUBLIC endpoint: /store/stores/public/
 * - Shows clean cards + CTA to enter store
 * - Investor-friendly presentation
 * ======================================================
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchPublicStores } from "../features/pos/pos.api";

export default function StorePickerPage() {
  const navigate = useNavigate();

  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    async function load() {
      setLoading(true);
      setErr("");
      try {
        // ✅ PUBLIC: Do NOT call staff fetchStores() here
        const list = await fetchPublicStores();
        setStores(Array.isArray(list) ? list : []);
      } catch (e) {
        setErr(e?.message || "Failed to load stores.");
        setStores([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return <div className="p-6 text-gray-600">Loading stores…</div>;
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border bg-white p-6">
        <h1 className="text-2xl font-semibold text-gray-900">Online Store</h1>
        <p className="text-gray-600 mt-2">
          Choose a branch to shop from. Stock and pricing are store-specific.
        </p>

        {err && (
          <div className="mt-4 border rounded p-3 text-sm border-red-200 bg-red-50 text-red-800">
            {err}
          </div>
        )}

        {!err && stores.length === 0 && (
          <div className="mt-4 text-gray-600">No stores available right now.</div>
        )}
      </div>

      {stores.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {stores.map((s) => (
            <div key={s.id} className="rounded-2xl border bg-white p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-lg font-semibold text-gray-900">{s.name}</div>
                  <div className="text-xs text-gray-500 mt-1">
                    Store ID: <span className="font-mono">{s.id}</span>
                  </div>
                </div>

                <span className="text-xs px-2 py-1 rounded-full border bg-green-50 text-green-700 border-green-200">
                  Active
                </span>
              </div>

              <div className="mt-4 flex gap-2">
                {/* ✅ FIX: Enter Store goes to the known working shop route */}
                <button
                  type="button"
                  onClick={() => navigate(`/store/${s.id}/shop`)}
                  className="flex-1 px-4 py-2 rounded-md bg-gray-900 text-white hover:bg-gray-800"
                >
                  Enter Store
                </button>

                <button
                  type="button"
                  onClick={() => navigate(`/store/${s.id}/shop`)}
                  className="px-4 py-2 rounded-md border hover:bg-gray-50"
                >
                  Shop
                </button>
              </div>

              <div className="mt-4 text-sm text-gray-600">
                Pharmacy • Retail • Multi-category ready
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-2xl border bg-white p-6">
        <div className="text-sm text-gray-700">
          <span className="font-semibold">Best practice:</span> this storefront is{" "}
          <span className="font-semibold">store-scoped</span> to keep stock and checkout
          correct. A global “all stores” catalog can be added later.
        </div>
      </div>
    </div>
  );
}
