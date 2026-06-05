export default function ReceiptHeader({ receiptNo }) {
  return (
    <div className="border-b pb-2 mb-2">
      <h2 className="text-center font-bold text-lg">PHARMACY RECEIPT</h2>
      <p className="text-sm">Date: {new Date().toLocaleString()}</p>
      <p className="text-sm">Receipt No: {receiptNo}</p>
    </div>
  );
}
