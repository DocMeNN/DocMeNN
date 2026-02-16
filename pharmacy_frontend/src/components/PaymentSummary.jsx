//src/components/PaymentSummary.jsx

import { formatMoney } from "../utils/money";

export default function PaymentSummary({ cart }) {
  const subtotal = cart.reduce(
    (sum, item) => sum + item.qty * item.price,
    0
  );

  const tax = subtotal * 0.075;
  const total = subtotal + tax;

  return (
    <div className="mt-4 border-t pt-3 text-sm">
      <div className="flex justify-between">
        <span>Subtotal:</span>
        <span>{formatMoney(subtotal)}</span>
      </div>

      <div className="flex justify-between">
        <span>VAT (7.5%):</span>
        <span>{formatMoney(tax)}</span>
      </div>

      <div className="flex justify-between font-bold text-lg mt-2">
        <span>Total:</span>
        <span>{formatMoney(total)}</span>
      </div>

      <div className="mt-3">
        <p className="font-semibold">Payment Method:</p>
        <p>Cash / POS / Transfer</p>
      </div>
    </div>
  );
}
