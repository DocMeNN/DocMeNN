/**
 * ======================================================
 * PATH: src/features/pos/CartPanel.jsx
 * ======================================================
 *
 * CartPanel (UI-only)
 * ------------------------------------------------------
 * - Renders current cart items + totals
 * - Exposes increment/decrement callbacks
 * - Exposes "New Sale / Clear Cart" intent
 * - No business logic (backend + store remain authoritative)
 * ======================================================
 */

import CartItem from "./CartItem";
import { formatMoney } from "../../utils/money";

export default function CartPanel({
  cart,
  onIncrement,
  onDecrement,
  onClearCart,
  disabled = false,
}) {
  const items = Array.isArray(cart?.items) ? cart.items : [];

  if (!cart || items.length === 0) {
    return (
      <div className="space-y-3">
        <p className="text-gray-500">Cart is empty</p>
        <button
          type="button"
          disabled={true}
          className="
            w-full py-2 rounded border
            text-gray-400 bg-gray-50
            cursor-not-allowed
          "
          title="Cart is already empty"
        >
          New Sale / Clear Cart
        </button>
      </div>
    );
  }

  const total = cart.total_amount ?? cart.subtotal_amount ?? 0;
  const itemCount = cart.item_count ?? items.length;

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <CartItem
          key={item.id}
          item={item}
          onIncrement={onIncrement}
          onDecrement={onDecrement}
          disabled={disabled}
        />
      ))}

      <div className="pt-3 border-t text-right space-y-2">
        <div className="text-sm text-gray-600">Items: {itemCount}</div>
        <div className="text-lg font-bold">Total: {formatMoney(total)}</div>

        <div className="pt-2">
          <button
            type="button"
            disabled={disabled}
            onClick={async () => {
              if (disabled) return;
              await onClearCart?.();
            }}
            className="
              w-full py-2 rounded
              border border-red-200
              bg-red-50 text-red-700 font-medium
              hover:bg-red-100
              disabled:opacity-40 disabled:cursor-not-allowed
              transition
            "
          >
            New Sale / Clear Cart
          </button>
        </div>
      </div>
    </div>
  );
}
