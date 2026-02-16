// src/components/accounting/BalanceSheetHeader.jsx

export default function BalanceSheetHeader({ asOf, balanced }) {
  return (
    <div className="mb-6 flex justify-between items-center">
      <div>
        <h2 className="text-xl font-semibold">Balance Sheet</h2>
        <p className="text-sm text-gray-500">
          As of {new Date(asOf).toLocaleString()}
        </p>
      </div>

      <span
        className={`px-3 py-1 rounded-full text-sm ${
          balanced
            ? "bg-green-100 text-green-700"
            : "bg-red-100 text-red-700"
        }`}
      >
        {balanced ? "Balanced" : "Out of Balance"}
      </span>
    </div>
  );
}
