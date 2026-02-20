/**
 * ======================================================
 * PATH: src/components/StoreSelector.jsx
 * ======================================================
 *
 * StoreSelector (STAFF)
 * ------------------------------------------------------
 * - Fetches active stores from backend
 * - Persists selection in localStorage
 * - REQUIRED for store-scoped POS + Inventory
 *
 * Storage key:
 *   localStorage.active_store_id
 *
 * Broadcast:
 * - dispatches window event "active-store-changed"
 *   detail: { storeId }
 *
 * Notes:
 * - Uses POS API contract (single source of network truth)
 * - Syncs across tabs via storage event
 * - Avoids re-fetch loops if parent passes inline onChange
 * ======================================================
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { fetchStaffStores } from "../features/pos/pos.api";

function resolveInitialStoreId() {
  return (
    String(localStorage.getItem("active_store_id") || "").trim() ||
    String(localStorage.getItem("store_id") || "").trim() ||
    ""
  );
}

function broadcastActiveStore(storeId) {
  try {
    window.dispatchEvent(
      new CustomEvent("active-store-changed", {
        detail: { storeId: storeId || "" },
      })
    );
  } catch {
    // no-op
  }
}

export default function StoreSelector({ onChange }) {
  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [activeStoreId, setActiveStoreId] = useState(resolveInitialStoreId);

  // Keep latest onChange without re-triggering effects
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  // Prevent duplicate broadcasts
  const lastBroadcastRef = useRef(null);

  const safeBroadcast = (sid) => {
    const next = String(sid || "").trim();
    if (lastBroadcastRef.current === next) return;
    lastBroadcastRef.current = next;
    broadcastActiveStore(next);
  };

  const activeStore = useMemo(() => {
    return stores.find((s) => String(s.id) === String(activeStoreId)) || null;
  }, [stores, activeStoreId]);

  // Load stores once on mount
  useEffect(() => {
    let mounted = true;

    async function loadStores() {
      setLoading(true);
      setError("");

      try {
        const list = await fetchStaffStores();
        if (!mounted) return;

        const active = (Array.isArray(list) ? list : []).filter(
          (s) => s?.is_active !== false
        );

        setStores(active);

        const saved = String(localStorage.getItem("active_store_id") || "").trim();

        // If saved storeId no longer exists, clear it (and broadcast)
        if (saved && !active.some((s) => String(s.id) === saved)) {
          localStorage.removeItem("active_store_id");
          localStorage.removeItem("store_id");

          setActiveStoreId("");
          safeBroadcast("");

          if (onChangeRef.current) onChangeRef.current("", null);
          return;
        }

        // Broadcast initial store ONCE (helps pages mount cleanly)
        const initial = resolveInitialStoreId();
        if (initial) {
          // keep state aligned if state is empty or stale
          setActiveStoreId((prev) => (String(prev || "").trim() ? prev : initial));
          safeBroadcast(initial);
        }
      } catch (e) {
        if (!mounted) return;
        setError(e?.message || "Failed to load stores.");
      } finally {
        if (!mounted) return;
        setLoading(false);
      }
    }

    loadStores();
    return () => {
      mounted = false;
    };
  }, []);

  // ✅ Sync when another tab changes the active store
  useEffect(() => {
    function onStorage(ev) {
      if (ev.key !== "active_store_id") return;

      const next = String(ev.newValue || "").trim();
      setActiveStoreId(next);
      safeBroadcast(next);
    }

    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const handleChange = (e) => {
    const storeId = String(e.target.value || "").trim();

    setActiveStoreId(storeId);

    if (storeId) localStorage.setItem("active_store_id", storeId);
    else localStorage.removeItem("active_store_id");

    // legacy alignment (optional)
    if (storeId) localStorage.setItem("store_id", storeId);
    else localStorage.removeItem("store_id");

    const storeObj =
      storeId && Array.isArray(stores)
        ? stores.find((s) => String(s.id) === String(storeId)) || null
        : null;

    safeBroadcast(storeId);

    if (onChangeRef.current) onChangeRef.current(storeId, storeObj);
  };

  if (loading) {
    return <p className="text-sm text-gray-500">Loading stores…</p>;
  }

  if (error) {
    return (
      <div className="border border-red-200 bg-red-50 p-2 text-sm text-red-700 rounded">
        {error}
      </div>
    );
  }

  if (stores.length === 0) {
    return (
      <div className="border border-yellow-200 bg-yellow-50 p-2 text-sm text-yellow-800 rounded">
        No active stores found. Create one in admin.
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <label className="text-sm font-medium text-gray-700">Active Store:</label>

      <select
        value={activeStoreId}
        onChange={handleChange}
        className="border px-3 py-2 rounded text-sm min-w-[220px]"
      >
        <option value="">— Select store —</option>
        {stores.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>

      {activeStore ? (
        <span className="text-xs text-gray-500">
          Selected:{" "}
          <span className="font-medium text-gray-700">{activeStore.name}</span>
        </span>
      ) : null}
    </div>
  );
}
