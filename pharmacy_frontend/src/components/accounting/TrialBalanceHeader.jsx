// src/components/accounting/TrialBalanceHeader.jsx

function formatAsOf(asOf) {
  if (!asOf) return "—";

  const d = new Date(asOf);
  if (Number.isNaN(d.getTime())) return "—";

  return d.toLocaleString();
}

export default function TrialBalanceHeader({ asOf, balanced }) {
  return (
    <div className="flex justify-between items-center mb-4">
      <div>
        <h2 className="text-xl font-semibold">Trial Balance</h2>
        <p className="text-sm text-gray-500">As of {formatAsOf(asOf)}</p>
      </div>

      <span
        className={`px-3 py-1 rounded-full text-sm ${
          balanced ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
        }`}
      >
        {balanced ? "Balanced" : "Out of Balance"}
      </span>
    </div>
  );
}
