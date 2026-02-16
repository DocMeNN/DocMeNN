// src/components/admin/AdminQuickActions.jsx


/**
 * ======================================================
 * PATH: src/components/admin/AdminQuickActions.jsx
 * ======================================================
 *
 * ADMIN QUICK ACTIONS
 * ------------------------------------------------------
 * Adds fast navigation cards for major admin workflows.
 * Includes:
 * - Inventory (general)
 * - Expiry Alerts (Phase 2 remaining UX item)
 * - Online Store
 * - Sales
 * - Accounting
 * ======================================================
 */

import { useNavigate } from "react-router-dom";
import DashboardCard from "../ui/DashboardCard";

export default function AdminQuickActions() {
  const navigate = useNavigate();

  return (
    <div>
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Quick Actions</h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* ✅ Staff inventory (manage stock/pricing) */}
        <DashboardCard
          title="Inventory"
          subtitle="Manage stock & pricing"
          actionLabel="Open"
          onAction={() => navigate("/inventory")}
        />

        {/* ✅ Expiry alerts (store-scoped; pass storeId via URL when available) */}
        <DashboardCard
          title="Expiry Alerts"
          subtitle="Expiring batches soon"
          actionLabel="Open"
          onAction={() => navigate("/inventory/expiry-alerts")}
        />

        {/* ✅ Public storefront */}
        <DashboardCard
          title="Online Store"
          subtitle="View storefront (public)"
          actionLabel="Open"
          onAction={() => navigate("/store")}
        />

        <DashboardCard
          title="Sales"
          subtitle="View sales history"
          actionLabel="Open"
          onAction={() => navigate("/sales")}
        />

        <DashboardCard
          title="Accounting"
          subtitle="Financial reports"
          actionLabel="View"
          onAction={() => navigate("/accounting/trial-balance")}
        />
      </div>
    </div>
  );
}
