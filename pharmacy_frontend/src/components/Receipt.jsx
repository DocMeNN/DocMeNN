import { useEffect, useRef } from "react";
import JsBarcode from "jsbarcode";

export default function Receipt({ cart, paymentMethod, receiptNumber }) {
  const barcodeRef = useRef(null);

  useEffect(() => {
    if (barcodeRef.current) {
      JsBarcode(barcodeRef.current, receiptNumber, {
        format: "CODE128",
        width: 2,
        height: 50,
      });
    }
  }, [receiptNumber]);

  const total = cart.reduce((sum, item) => sum + item.qty * item.price, 0);

  return (
    <div>
      <h2>PHARMACY RECEIPT</h2>
      <p>Receipt No: <strong>{receiptNumber}</strong></p>
      <p>Payment Method: <strong>{paymentMethod}</strong></p>
      <svg ref={barcodeRef}></svg>

      <table>
        <thead>
          <tr>
            <th>Item</th><th>Qty</th><th>Price</th>
          </tr>
        </thead>
        <tbody>
          {cart.map(item => (
            <tr key={item.id}>
              <td>{item.name}</td>
              <td>{item.qty}</td>
              <td>{(item.qty * item.price).toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Total: ₦{total.toFixed(2)}</h3>
    </div>
  );
}
