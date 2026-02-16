// src/components/admin/AdminKpiCards.jsx

import DashboardCard from "../ui/DashboardCard";
import { formatMoney } from "../../utils/money";

/**
 * Admin KPI Cards (Data-driven)
 *
 * Props:
 * - kpis: {
 *     total_sales_today?: number,
 *     items_in_stock?: number,
 *     outstanding_bills?: number,
 *     net_profit_mtd?: number,
 *   }
 * - isLoading?: boolean
 * - errorMessage?: string | null
 */
export default function AdminKpiCards({
  kpis,
  isLoading = false,
  errorMessage = null,
}) {
  // Never lie with "₦0" when we're loading or failing.
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <DashboardCard title="Total Sales Today" value="…" subtitle="Gross revenue" />
        <DashboardCard title="Items in Stock" value="…" subtitle="Active inventory" />
        <DashboardCard title="Outstanding Bills" value="…" subtitle="Unsettled transactions" />
        <DashboardCard title="Net Profit (MTD)" value="…" subtitle="After expenses" highlight />
      </div>
    );
  }

  if (errorMessage) {
    return (
      <div className="rounded-lg border bg-white p-4">
        <p className="text-sm font-medium text-gray-800">Couldn’t load Admin KPIs</p>
        <p className="text-sm text-gray-600 mt-1">{errorMessage}</p>
      </div>
    );
  }

  const totalSalesToday = Number(kpis?.total_sales_today ?? 0);
  const itemsInStock = Number(kpis?.items_in_stock ?? 0);
  const outstandingBills = Number(kpis?.outstanding_bills ?? 0);
  const netProfitMtd = Number(kpis?.net_profit_mtd ?? 0);

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
      <DashboardCard
        title="Total Sales Today"
        value={formatMoney(totalSalesToday)}
        subtitle="Gross revenue"
      />

      <DashboardCard
        title="Items in Stock"
        value={String(itemsInStock)}
        subtitle="Active inventory"
      />

      <DashboardCard
        title="Outstanding Bills"
        value={formatMoney(outstandingBills)}
        subtitle="Unsettled transactions"
      />

      <DashboardCard
        title="Net Profit (MTD)"
        value={formatMoney(netProfitMtd)}
        subtitle="After expenses"
        highlight
      />
    </div>
  );
}
