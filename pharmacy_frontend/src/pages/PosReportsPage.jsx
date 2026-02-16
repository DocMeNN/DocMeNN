// src/pages/PosReportsPage.jsx

import { useEffect, useMemo, useState } from "react";
import { formatMoney } from "../utils/money";
import {
  fetchDailySalesReport,
  fetchCashReconReport,
  fetchZReport,
} from "../features/reports/posReports.api";

function todayISO() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function PosReportsPage() {
  const [tab, setTab] = useState("daily"); // daily | cash | z
  const [date, setDate] = useState(todayISO());

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [daily, setDaily] = useState(null);
  const [cashRecon, setCashRecon] = useState(null);
  const [zReport, setZReport] = useState(null);

  const title = useMemo(() => {
    if (tab === "daily") return "Daily Sales";
    if (tab === "cash") return "Cash Reconciliation";
    return "Z-Report";
  }, [tab]);

  const load = async () => {
    setLoading(true);
    setError("");

    try {
      if (tab === "daily") {
        const data = await fetchDailySalesReport({ date });
        setDaily(data);
      } else if (tab === "cash") {
        const data = await fetchCashReconReport({ date });
        setCashRecon(data);
      } else {
        const data = await fetchZReport({ date });
        setZReport(data);
      }
    } catch (e) {
      setError(e?.message || "Failed to load report.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, date]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">POS Reports</h2>
          <p className="text-sm text-gray-600">
            Operational sales reports (Phase 1.4)
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div>
            <label className="block text-xs text-gray-600 mb-1">Report date</label>
            <input
              type="date"
              className="border rounded px-3 py-2"
              value={date}
              onChange={(e) => setDate(e.target.value)}
            />
          </div>

          <button
            type="button"
            onClick={load}
            className="border rounded px-4 py-2 hover:bg-gray-50"
            disabled={loading}
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 border-b">
        <Tab label="Daily Sales" active={tab === "daily"} onClick={() => setTab("daily")} />
        <Tab label="Cash Recon" active={tab === "cash"} onClick={() => setTab("cash")} />
        <Tab label="Z-Report" active={tab === "z"} onClick={() => setTab("z")} />
      </div>

      {error && (
        <div className="border border-red-200 bg-red-50 text-red-800 rounded p-3 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="p-4 text-gray-600">Loading {title}…</div>
      ) : (
        <div className="bg-white border rounded-xl p-5">
          {tab === "daily" && <DailySalesView data={daily} />}
          {tab === "cash" && <CashReconView data={cashRecon} />}
          {tab === "z" && <ZReportView data={zReport} />}
        </div>
      )}
    </div>
  );
}

function Tab({ label, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`pb-2 px-1 border-b-2 transition ${
        active
          ? "border-gray-900 text-gray-900 font-semibold"
          : "border-transparent text-gray-500 hover:text-gray-900"
      }`}
    >
      {label}
    </button>
  );
}

function Stat({ label, value }) {
  return (
    <div className="border rounded-lg p-3">
      <div className="text-xs text-gray-600">{label}</div>
      <div className="text-lg font-semibold mt-1">{value}</div>
    </div>
  );
}

function DailySalesView({ data }) {
  if (!data) return <p className="text-gray-600">No data.</p>;

  const gross = data.gross || {};
  const refunds = data.refunds || {};
  const net = data.net || {};

  const byPay = data?.breakdowns?.by_payment_method || [];
  const byCashier = data?.breakdowns?.by_cashier || [];

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">Daily Sales • {data.date}</h3>
        <p className="text-sm text-gray-600">Gross, refunds, and net totals.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Stat label="Sales count" value={gross.sales_count ?? 0} />
        <Stat label="Gross total" value={formatMoney(gross.total_amount ?? 0)} />
        <Stat label="Refund total" value={formatMoney(refunds.refund_total_amount ?? 0)} />
        <Stat label="Net total" value={formatMoney(net.net_total_amount ?? 0)} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h4 className="font-semibold mb-2">By Payment Method</h4>
          <Table
            columns={["Payment", "Count", "Total"]}
            rows={byPay.map((r) => [
              r.payment_method,
              r.count,
              formatMoney(r.total_amount ?? 0),
            ])}
            empty="No sales for this date."
          />
        </div>

        <div>
          <h4 className="font-semibold mb-2">By Cashier</h4>
          <Table
            columns={["Cashier", "Count", "Total"]}
            rows={byCashier.map((r) => [
              r.display_name || r.email || "Unknown",
              r.count,
              formatMoney(r.total_amount ?? 0),
            ])}
            empty="No cashier activity for this date."
          />
        </div>
      </div>
    </div>
  );
}

function CashReconView({ data }) {
  if (!data) return <p className="text-gray-600">No data.</p>;

  const byPay = data.by_payment_method || [];

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">Cash Reconciliation • {data.date}</h3>
        <p className="text-sm text-gray-600">Cash vs non-cash totals.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Stat label="Cash total" value={formatMoney(data.cash_total_amount ?? 0)} />
        <Stat label="Non-cash total" value={formatMoney(data.non_cash_total_amount ?? 0)} />
      </div>

      <div>
        <h4 className="font-semibold mb-2">Payment Breakdown</h4>
        <Table
          columns={["Payment", "Count", "Total"]}
          rows={byPay.map((r) => [
            r.payment_method,
            r.count,
            formatMoney(r.total_amount ?? 0),
          ])}
          empty="No sales for this date."
        />
      </div>
    </div>
  );
}

function ZReportView({ data }) {
  if (!data) return <p className="text-gray-600">No data.</p>;

  const z = data.z_report || {};

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold">Z-Report • {data.date}</h3>
          <p className="text-sm text-gray-600">
            Daily close snapshot (shift sessions can be added later).
          </p>
        </div>

        <button
          type="button"
          onClick={() => window.print()}
          className="border rounded px-4 py-2 hover:bg-gray-50"
        >
          Print
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Stat label="Transactions" value={z.transaction_count ?? 0} />
        <Stat label="Gross total" value={formatMoney(z.gross_total_amount ?? 0)} />
        <Stat label="Refund total" value={formatMoney(z.refund_total_amount ?? 0)} />
        <Stat label="Net total" value={formatMoney(z.net_total_amount ?? 0)} />
      </div>

      <div className="text-xs text-gray-500">
        Generated at: {data.generated_at}
      </div>
    </div>
  );
}

function Table({ columns, rows, empty }) {
  if (!rows || rows.length === 0) {
    return <p className="text-gray-500 text-sm">{empty}</p>;
  }

  return (
    <div className="border rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-gray-700">
          <tr>
            {columns.map((c) => (
              <th key={c} className="text-left font-semibold px-3 py-2 border-b">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, idx) => (
            <tr key={idx} className="odd:bg-white even:bg-gray-50">
              {r.map((cell, i) => (
                <td key={i} className="px-3 py-2 border-b last:border-b-0">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
