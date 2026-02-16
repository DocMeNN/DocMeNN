// src/features/pos/CartItem.jsx

/**
 * ======================================================
 * PATH: src/features/pos/CartItem.jsx
 * ======================================================
 *
 * CartItem (UI-only)
 * ------------------------------------------------------
 * - Pure presentational component
 * - Emits intent only (increment / decrement)
 * - Never assumes pricing or stock rules
 * - Locally guards against rapid double clicks
 *
 * Money rule:
 * - Frontend displays money only; backend is authoritative.
 * ======================================================
 */

import { useEffect, useMemo, useState } from "react";
import { formatMoney } from "../../utils/money";

export default function CartItem({ item, onIncrement, onDecrement, disabled = false }) {
  if (!item || typeof item !== "object") return null;

  const productName = item.product_name ?? item.name ?? "Unnamed item";
  const qty = Math.max(0, Number(item.quantity ?? 0));

  // Prefer line_total if backend provides it (avoid recomputing money in UI).
  // Fallback to unit_price * qty for display only.
  const unitPrice = Number(item.unit_price ?? 0);

  const lineTotal = useMemo(() => {
    const serverLine = item.line_total ?? item.total_amount ?? null;
    if (serverLine != null && serverLine !== "") return Number(serverLine) || 0;
    return (Number(unitPrice) || 0) * qty;
  }, [item, unitPrice, qty]);

  const [localLock, setLocalLock] = useState(false);

  // If store disables, immediately unlock local
  useEffect(() => {
    if (disabled) setLocalLock(false);
  }, [disabled]);

  const locked = disabled || localLock;

  const run = async (fn) => {
    if (locked) return;
    setLocalLock(true);
    try {
      await fn?.(item);
    } finally {
      // Small delay smooths out jitter from rapid scanning/clicking
      setTimeout(() => setLocalLock(false), 120);
    }
  };

  return (
    <div className="flex justify-between items-center border p-3 rounded bg-white">
      <div className="space-y-1">
        <p className="font-semibold">{productName}</p>

        <p className="text-sm text-gray-600">
          {formatMoney(unitPrice)} × {qty}
          <span className="mx-2 text-gray-300">•</span>
          <span className="text-gray-800 font-medium">{formatMoney(lineTotal)}</span>
        </p>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={locked || qty <= 0}
          onClick={() => run(onDecrement)}
          className="
            px-3 py-1 rounded border text-lg
            hover:bg-gray-50 active:bg-gray-100
            disabled:opacity-40 disabled:cursor-not-allowed
            transition
          "
          aria-label={`Decrease ${productName}`}
        >
          −
        </button>

        <span className="min-w-[28px] text-center font-medium">{qty}</span>

        <button
          type="button"
          disabled={locked}
          onClick={() => run(onIncrement)}
          className="
            px-3 py-1 rounded border text-lg
            hover:bg-gray-50 active:bg-gray-100
            disabled:opacity-40 disabled:cursor-not-allowed
            transition
          "
          aria-label={`Increase ${productName}`}
        >
          +
        </button>
      </div>
    </div>
  );
}
