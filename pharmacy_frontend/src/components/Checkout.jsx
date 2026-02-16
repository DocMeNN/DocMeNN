import { useState } from "react";
import ReceiptModal from "./ReceiptModal";
import { api } from "../api/api";

export default function Checkout({ cart, clearCart }) {
  const [paymentMethod, setPaymentMethod] = useState("Cash");
  const [showReceipt, setShowReceipt] = useState(false);
  const [receiptNumber, setReceiptNumber] = useState("");

  async function handlePayment() {
    if (cart.length === 0) {
      alert("Cart is empty");
      return;
    }

    // Create unique receipt number
    const receiptNo = "RCPT-" + Date.now();
    setReceiptNumber(receiptNo);

    // Save to backend
    await api("/api/pos/sale/", "POST", {
      receipt_no: receiptNo,
      payment_method: paymentMethod,
      items: cart,
    });

    setShowReceipt(true);
  }

  function closeReceipt() {
    setShowReceipt(false);
    clearCart();
  }

  return (
    <div className="p-4 mt-4 bg-white shadow rounded-lg">
      <h2 className="text-xl font-bold">Checkout</h2>

      {/* Payment Method Select */}
      <select
        value={paymentMethod}
        onChange={(e) => setPaymentMethod(e.target.value)}
        className="border p-2 mt-3"
      >
        <option>Cash</option>
        <option>POS</option>
        <option>Transfer</option>
      </select>

      <button
        onClick={handlePayment}
        className="px-4 py-2 mt-4 bg-green-600 text-white rounded"
      >
        Payment Complete
      </button>

      {showReceipt && (
        <ReceiptModal
          cart={cart}
          paymentMethod={paymentMethod}
          receiptNumber={receiptNumber}
          onClose={closeReceipt}
        />
      )}
    </div>
  );
}
