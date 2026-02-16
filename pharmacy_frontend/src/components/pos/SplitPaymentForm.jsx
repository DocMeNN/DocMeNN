// src/components/pos/SplitPaymentForm.jsx
import { useMemo } from "react";
import { toCents, centsToAmountString, sumCents } from "../../utils/moneyMath";
import { formatMoney } from "../../utils/money";

const METHODS = [
  { value: "cash", label: "Cash" },
  { value: "bank", label: "Bank" },
  { value: "pos", label: "POS" },
  { value: "transfer", label: "Transfer" },
  { value: "credit", label: "Credit" },
];

export default function SplitPaymentForm({
  totalAmount,              // number (naira) or string
  allocations,
  setAllocations,
}) {
  const totalCents = useMemo(() => toCents(totalAmount), [totalAmount]);
  const allocatedCents = useMemo(() => sumCents(allocations), [allocations]);

  const remainingCents = totalCents - allocatedCents;

  const canSubmit = useMemo(() => {
    if (!allocations?.length) return false;
    if (allocatedCents !== totalCents) return false;
    return allocations.every((a) => a.method && Number(a.amountCents) > 0);
  }, [allocations, allocatedCents, totalCents]);

  function updateLine(idx, patch) {
    setAllocations((prev) =>
      prev.map((x, i) => (i === idx ? { ...x, ...patch } : x))
    );
  }

  function addLine() {
    setAllocations((prev) => [
      ...(prev || []),
      { method: "cash", amountCents: 0, reference: "", note: "" },
    ]);
  }

  function removeLine(idx) {
    setAllocations((prev) => prev.filter((_, i) => i !== idx));
  }

  function fillRemaining(idx) {
    const current = Number(allocations?.[idx]?.amountCents) || 0;
    const newCents = Math.max(0, current + remainingCents);
    updateLine(idx, { amountCents: newCents });
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border bg-white p-4">
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-600">Total Due</p>
          <p className="text-lg font-semibold">{formatMoney(totalAmount)}</p>
        </div>

        <div className="flex items-center justify-between mt-2">
          <p className="text-sm text-gray-600">Allocated</p>
          <p className="text-sm font-medium">
            {formatMoney(centsToAmountString(allocatedCents))}
          </p>
        </div>

        <div className="flex items-center justify-between mt-1">
          <p className="text-sm text-gray-600">Remaining</p>
          <p className={`text-sm font-medium ${remainingCents === 0 ? "text-green-700" : "text-red-700"}`}>
            {formatMoney(centsToAmountString(remainingCents))}
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {(allocations || []).map((a, idx) => (
          <div key={idx} className="rounded-lg border bg-white p-4 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div>
                <label className="text-xs text-gray-500">Method</label>
                <select
                  className="w-full border rounded-md px-3 py-2"
                  value={a.method}
                  onChange={(e) => updateLine(idx, { method: e.target.value })}
                >
                  {METHODS.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs text-gray-500">Amount</label>
                <input
                  className="w-full border rounded-md px-3 py-2"
                  inputMode="decimal"
                  value={centsToAmountString(a.amountCents || 0)}
                  onChange={(e) => updateLine(idx, { amountCents: toCents(e.target.value) })}
                />
              </div>

              <div>
                <label className="text-xs text-gray-500">Reference</label>
                <input
                  className="w-full border rounded-md px-3 py-2"
                  value={a.reference || ""}
                  onChange={(e) => updateLine(idx, { reference: e.target.value })}
                  placeholder="Optional"
                />
              </div>

              <div>
                <label className="text-xs text-gray-500">Note</label>
                <input
                  className="w-full border rounded-md px-3 py-2"
                  value={a.note || ""}
                  onChange={(e) => updateLine(idx, { note: e.target.value })}
                  placeholder="Optional"
                />
              </div>
            </div>

            <div className="flex gap-2 justify-between">
              <button
                type="button"
                className="text-sm px-3 py-2 rounded-md border"
                onClick={() => fillRemaining(idx)}
              >
                Fill Remaining
              </button>

              <button
                type="button"
                className="text-sm px-3 py-2 rounded-md border text-red-700"
                onClick={() => removeLine(idx)}
                disabled={(allocations || []).length <= 1}
              >
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>

      <button
        type="button"
        className="w-full px-4 py-3 rounded-md bg-gray-900 text-white disabled:opacity-50"
        onClick={addLine}
      >
        Add Payment Line
      </button>

      {!canSubmit && (
        <p className="text-sm text-gray-600">
          Split payment must fully match the total (no remaining balance).
        </p>
      )}
    </div>
  );
}
