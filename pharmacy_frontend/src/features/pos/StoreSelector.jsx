// src/features/pos/StoreSelector.jsx

/**
 * ======================================================
 * PATH: src/features/pos/StoreSelector.jsx
 * ======================================================
 *
 * STORE SELECTOR (DUMB UI COMPONENT)
 *
 * Contract:
 * - Receives stores[] + current value + onChange(storeId|null)
 * - Does NOT fetch stores (PosPage/usePosStore handles that)
 * - Persists active store id to localStorage (active_store_id)
 * - Broadcasts a global event "active-store-changed" so any page
 *   (Inventory, POS, etc.) can react immediately if needed.
 *
 * Golden rules:
 * - Store-scoped operations always depend on active_store_id
 * - Keep this component simple: no side effects beyond selection
 */

export default function StoreSelector({
  stores = [],
  value,
  onChange,
  disabled = false,
  loading = false,
}) {
  const list = Array.isArray(stores) ? stores : [];
  const hasStores = list.length > 0;

  const handleChange = (e) => {
    const sid = e.target.value || "";

    // Persist selection (single source of store context)
    if (sid) localStorage.setItem("active_store_id", sid);
    else localStorage.removeItem("active_store_id");

    // Broadcast for any listeners (optional pattern)
    // e.g., Inventory page, headers, other tabs, etc.
    window.dispatchEvent(
      new CustomEvent("active-store-changed", { detail: { storeId: sid || null } })
    );

    onChange?.(sid || null);
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="text-sm font-medium text-gray-700">Store:</div>

      <select
        className="border px-3 py-2 rounded min-w-[260px] bg-white"
        value={value || ""}
        disabled={disabled || loading || !hasStores}
        onChange={handleChange}
      >
        <option value="">
          {loading
            ? "Loading stores…"
            : hasStores
            ? "Select a store…"
            : "No stores found"}
        </option>

        {list.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>

      {!value && (
        <span className="text-xs text-gray-500">
          Pick a store before adding items / checkout.
        </span>
      )}
    </div>
  );
}
