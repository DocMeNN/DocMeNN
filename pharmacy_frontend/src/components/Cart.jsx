//src/components/cart.jsx

import { formatMoney } from "../utils/money";

export default function Cart({ cart, updateQty, removeItem }) {
  const subtotal = cart.reduce(
    (sum, item) => sum + item.price * item.qty,
    0
  );

  const VAT_RATE = 0.075; // 7.5%
  const DISCOUNT = 0.05; // 5%

  const vat = subtotal * VAT_RATE;
  const discount = subtotal * DISCOUNT;
  const total = subtotal + vat - discount;

  return (
    <div className="p-4 bg-white shadow rounded">
      <h2 className="text-xl font-semibold mb-2">Cart</h2>

      {cart.length === 0 && <p>No items added.</p>}

      {cart.map((item) => (
        <div
          key={item.id}
          className="flex justify-between mb-3 border-b pb-2"
        >
          <div>
            <p className="font-medium">{item.name}</p>
            <p className="text-sm text-gray-500">
              {formatMoney(item.price)}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <input
              type="number"
              value={item.qty}
              onChange={(e) =>
                updateQty(item.id, Number(e.target.value))
              }
              className="w-16 border rounded px-2"
            />
            <button
              onClick={() => removeItem(item.id)}
              className="text-red-500 font-bold"
            >
              X
            </button>
          </div>
        </div>
      ))}

      <hr className="my-2" />

      <p>Subtotal: {formatMoney(subtotal)}</p>
      <p>VAT (7.5%): {formatMoney(vat)}</p>
      <p>Discount (5%): -{formatMoney(discount)}</p>

      <h2 className="text-lg font-bold mt-3">
        Total: {formatMoney(total)}
      </h2>
    </div>
  );
}
