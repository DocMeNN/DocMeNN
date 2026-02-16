// src/components/accounting/ProfitAndLossHeader.jsx

import { formatMoney } from "../../utils/money";

function formatPeriodValue(value) {
  if (!value) return "—";

  // If backend sends "YYYY-MM-DD", display as date (no timezone shift)
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value.trim())) {
    return value;
  }

  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);

  return d.toLocaleString();
}

export default function ProfitAndLossHeader({ period, netProfit }) {
  const start = period?.start_date ?? period?.from ?? null;
  const end = period?.end_date ?? period?.to ?? null;

  return (
    <div className="mb-2">
      <h2 className="text-xl font-semibold">Profit &amp; Loss Statement</h2>

      {(start || end) && (
        <p className="text-sm text-gray-500 mt-1">
          Period: {formatPeriodValue(start)} → {formatPeriodValue(end)}
        </p>
      )}

      <div className="mt-4 p-4 rounded bg-gray-100 font-semibold flex justify-between">
        <span>Net Profit</span>
        <span>{formatMoney(netProfit)}</span>
      </div>
    </div>
  );
}
