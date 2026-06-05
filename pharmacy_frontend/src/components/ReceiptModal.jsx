import { useRef } from "react";
import Receipt from "./Receipt";

export default function ReceiptModal({ cart, paymentMethod, receiptNumber, onClose }) {
  const printArea = useRef(null);

  function handlePrint() {
    const printContents = printArea.current.innerHTML;
    const win = window.open("", "", "width=800,height=600");

    win.document.write(`
      <html>
        <head>
          <title>Receipt</title>
          <style>
            body { font-family: Arial; padding: 20px; }
            table { width: 100%; border-collapse: collapse; }
            td, th { padding: 6px; border-bottom: 1px solid #ccc; }
            h2, p { margin: 0; }
          </style>
        </head>
        <body>${printContents}</body>
      </html>
    `);

    win.document.close();
    win.print();
    win.close();
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center">
      <div className="bg-white p-6 rounded shadow-lg w-[350px]">
        <div ref={printArea}>
          <Receipt
            cart={cart}
            paymentMethod={paymentMethod}
            receiptNumber={receiptNumber}
          />
        </div>

        <div className="flex justify-between mt-4">
          <button onClick={handlePrint} className="px-4 py-2 bg-blue-600 text-white rounded">
            Print
          </button>
          <button onClick={onClose} className="px-4 py-2 bg-gray-600 text-white rounded">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
