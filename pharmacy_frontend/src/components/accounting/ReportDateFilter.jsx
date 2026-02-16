// src/components/accounting/ReportDateFilter.jsx

function todayISO() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function firstDayOfMonthISO(date = new Date()) {
  const d = new Date(date.getFullYear(), date.getMonth(), 1);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function lastDayOfMonthISO(date = new Date()) {
  const d = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function firstDayOfYearISO(date = new Date()) {
  const y = date.getFullYear();
  return `${y}-01-01`;
}

/**
 * ReportDateFilter
 *
 * Modes:
 * - "range": start_date/end_date (P&L)
 * - "asOf": as_of_date (Balance Sheet)
 * - "asOfDateTime": as_of (Trial Balance; UI collects date, page converts to datetime)
 */
export default function ReportDateFilter({
  mode = "range",
  startDate,
  endDate,
  asOfDate,
  onChange,
  showPresets = true,
}) {
  const today = todayISO();

  const isRange = mode === "range";
  const isAsOf = mode === "asOf" || mode === "asOfDateTime";

  function setThisMonth() {
    const now = new Date();
    const start = firstDayOfMonthISO(now);
    const end = lastDayOfMonthISO(now);
    onChange?.({ startDate: start, endDate: end, asOfDate });
  }

  function setLastMonth() {
    const now = new Date();
    const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const start = firstDayOfMonthISO(lastMonth);
    const end = lastDayOfMonthISO(lastMonth);
    onChange?.({ startDate: start, endDate: end, asOfDate });
  }

  function setYTD() {
    const start = firstDayOfYearISO(new Date());
    const end = today;
    onChange?.({ startDate: start, endDate: end, asOfDate });
  }

  function setAsOfToday() {
    onChange?.({ startDate, endDate, asOfDate: today });
  }

  function reset() {
    if (isRange) onChange?.({ startDate: "", endDate: "", asOfDate });
    if (isAsOf) onChange?.({ startDate, endDate, asOfDate: "" });
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-4">
        {isRange && (
          <>
            <label className="block">
              <span className="block text-xs text-gray-500 mb-1">Start date</span>
              <input
                type="date"
                value={startDate || ""}
                onChange={(e) =>
                  onChange?.({ startDate: e.target.value, endDate, asOfDate })
                }
                className="border rounded-lg px-3 py-2"
              />
            </label>

            <label className="block">
              <span className="block text-xs text-gray-500 mb-1">End date</span>
              <input
                type="date"
                value={endDate || ""}
                onChange={(e) =>
                  onChange?.({ startDate, endDate: e.target.value, asOfDate })
                }
                className="border rounded-lg px-3 py-2"
              />
            </label>
          </>
        )}

        {isAsOf && (
          <label className="block">
            <span className="block text-xs text-gray-500 mb-1">As of</span>
            <input
              type="date"
              value={asOfDate || ""}
              onChange={(e) =>
                onChange?.({ startDate, endDate, asOfDate: e.target.value })
              }
              className="border rounded-lg px-3 py-2"
            />
          </label>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={reset}
            className="px-3 py-2 rounded-lg border hover:bg-gray-50 text-sm"
          >
            Reset
          </button>
        </div>
      </div>

      {showPresets && (
        <div className="flex flex-wrap gap-2">
          {isRange && (
            <>
              <button
                type="button"
                onClick={setThisMonth}
                className="px-3 py-2 rounded-lg border hover:bg-gray-50 text-sm"
              >
                This month
              </button>
              <button
                type="button"
                onClick={setLastMonth}
                className="px-3 py-2 rounded-lg border hover:bg-gray-50 text-sm"
              >
                Last month
              </button>
              <button
                type="button"
                onClick={setYTD}
                className="px-3 py-2 rounded-lg border hover:bg-gray-50 text-sm"
              >
                YTD
              </button>
            </>
          )}

          {isAsOf && (
            <button
              type="button"
              onClick={setAsOfToday}
              className="px-3 py-2 rounded-lg border hover:bg-gray-50 text-sm"
            >
              Today
            </button>
          )}
        </div>
      )}
    </div>
  );
}
