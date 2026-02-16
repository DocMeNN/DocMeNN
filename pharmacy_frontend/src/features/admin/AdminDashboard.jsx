// src/features/admin/AdminDashboard.jsx

import { Outlet } from "react-router-dom";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import AdminKpiCards from "../../components/admin/AdminKpiCards";
import AdminQuickActions from "../../components/admin/AdminQuickActions";

import { fetchProducts } from "../../api/products";
import { fetchDailySalesReport } from "../reports/posReports.api";
import { fetchAccountingOverviewKPIs, fetchExpenses } from "../../api/accounting";
import axiosClient from "../../api/axiosClient";

function todayISO() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function getErrorMessage(err, fallback) {
  return (
    err?.response?.data?.detail ||
    err?.response?.data?.error?.message ||
    err?.message ||
    fallback
  );
}

function normalizeProducts(data) {
  const raw = Array.isArray(data)
    ? data
    : Array.isArray(data?.results)
    ? data.results
    : [];

  return raw.map((p) => {
    const stock =
      p.total_stock ??
      p.stock ??
      p.quantity ??
      p.available_quantity ??
      p.available_stock ??
      0;

    const isActive = typeof p.is_active === "boolean" ? p.is_active : true;

    return { id: p.id, stock: Number(stock) || 0, isActive };
  });
}

function pickNumber(obj, keys, fallback = 0) {
  for (const k of keys) {
    const v = obj?.[k];
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}

function normalizeExpenses(data) {
  const raw = Array.isArray(data)
    ? data
    : Array.isArray(data?.results)
    ? data.results
    : [];
  return raw.map((e) => ({
    paymentMethod: String(e?.payment_method || e?.payment || "").toLowerCase(),
    amount: Number(e?.amount ?? 0) || 0,
  }));
}

function extractSalesArray(data) {
  if (!data) return [];
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  return [];
}

function isSameISODate(isoDate, isoDateTime) {
  if (!isoDate || !isoDateTime) return false;
  const s = String(isoDateTime);
  // Accept "YYYY-MM-DD..." or full ISO datetime
  return s.startsWith(`${isoDate}`);
}

/**
 * Sales Today Resolver
 * 1) Try POS Daily Sales report (fast + already structured)
 * 2) If endpoint is missing (404), fallback to staff sales list /sales/sales/
 */
async function fetchSalesToday({ date }) {
  try {
    const data = await fetchDailySalesReport({ date });

    const grossTotal = pickNumber(
      data?.gross,
      ["total_amount"],
      pickNumber(data, ["gross_total_amount", "total_amount", "total_sales_today"], 0)
    );

    return { grossTotal, source: "pos_daily_report" };
  } catch (err) {
    const status = err?.response?.status;

    // Fallback only for 404 (endpoint not found)
    if (status !== 404) throw err;

    // Fallback: compute from staff sales list
    // NOTE: This assumes backend returns sales with created_at and total_amount.
    const res = await axiosClient.get("/sales/sales/");
    const sales = extractSalesArray(res?.data);

    // Filter to "today"
    const todaysSales = sales.filter((s) => isSameISODate(date, s?.created_at));

    // Optional: only count completed sales if your backend has statuses
    const included = todaysSales.filter((s) => {
      const st = String(s?.status || "").toLowerCase();
      return !st || st === "completed" || st === "paid" || st === "done";
    });

    const grossTotal = included.reduce((sum, s) => {
      const n = Number(s?.total_amount ?? 0);
      return sum + (Number.isFinite(n) ? n : 0);
    }, 0);

    return { grossTotal, source: "sales_list_fallback" };
  }
}

export default function AdminDashboard() {
  const asOfDate = todayISO();

  // 1) Sales Today (with 404-safe fallback)
  const salesQuery = useQuery({
    queryKey: ["admin", "kpis", "sales-today", asOfDate],
    queryFn: () => fetchSalesToday({ date: asOfDate }),
    retry: 1,
    refetchOnWindowFocus: false,
  });

  // 2) Items in Stock
  const productsQuery = useQuery({
    queryKey: ["admin", "kpis", "products"],
    queryFn: fetchProducts,
    retry: 1,
    refetchOnWindowFocus: false,
  });

  // 3) Net Profit (MTD) via accounting overview
  const accountingKpiQuery = useQuery({
    queryKey: ["admin", "kpis", "accounting-overview", asOfDate],
    queryFn: () => fetchAccountingOverviewKPIs({ as_of_date: asOfDate }),
    retry: 1,
    refetchOnWindowFocus: false,
  });

  // 4) Outstanding Bills (Accounts Payable exposure) via credit expenses
  const expensesQuery = useQuery({
    queryKey: ["admin", "kpis", "expenses"],
    queryFn: () => fetchExpenses(),
    retry: 1,
    refetchOnWindowFocus: false,
  });

  const isLoading =
    salesQuery.isLoading ||
    productsQuery.isLoading ||
    accountingKpiQuery.isLoading ||
    expensesQuery.isLoading;

  const isError =
    salesQuery.isError ||
    productsQuery.isError ||
    accountingKpiQuery.isError ||
    expensesQuery.isError;

  const errorMessage = useMemo(() => {
    if (!isError) return null;

    // Make the error actionable: indicate which block failed + status code if available
    const parts = [];

    if (salesQuery.isError) {
      const st = salesQuery.error?.response?.status;
      parts.push(`Sales Today: ${getErrorMessage(salesQuery.error, "Failed")} (${st || "?"})`);
    }
    if (productsQuery.isError) {
      const st = productsQuery.error?.response?.status;
      parts.push(`Inventory: ${getErrorMessage(productsQuery.error, "Failed")} (${st || "?"})`);
    }
    if (accountingKpiQuery.isError) {
      const st = accountingKpiQuery.error?.response?.status;
      parts.push(`Net Profit: ${getErrorMessage(accountingKpiQuery.error, "Failed")} (${st || "?"})`);
    }
    if (expensesQuery.isError) {
      const st = expensesQuery.error?.response?.status;
      parts.push(`Bills: ${getErrorMessage(expensesQuery.error, "Failed")} (${st || "?"})`);
    }

    return parts.join(" • ") || "Failed to load Admin KPIs.";
  }, [
    isError,
    salesQuery.isError,
    salesQuery.error,
    productsQuery.isError,
    productsQuery.error,
    accountingKpiQuery.isError,
    accountingKpiQuery.error,
    expensesQuery.isError,
    expensesQuery.error,
  ]);

  const kpis = useMemo(() => {
    // Sales Today gross total
    const totalSalesToday = Number(salesQuery.data?.grossTotal ?? 0) || 0;

    // Items in Stock
    const products = normalizeProducts(productsQuery.data);
    const itemsInStock = products
      .filter((p) => p.isActive)
      .reduce((sum, p) => sum + (p.stock || 0), 0);

    // Net Profit (MTD)
    const overview = accountingKpiQuery.data || {};
    const netProfitMtd = pickNumber(
      overview,
      [
        "net_profit_mtd",
        "net_profit",
        "net_profit_month_to_date",
        "profit_mtd",
        "mtd_net_profit",
        "net_income_mtd",
        "net_income_month_to_date",
      ],
      0
    );

    // Outstanding Bills = total CREDIT expenses (AP exposure)
    const expenses = normalizeExpenses(expensesQuery.data);
    const outstandingBills = expenses
      .filter((e) => e.paymentMethod === "credit")
      .reduce((sum, e) => sum + (e.amount || 0), 0);

    return {
      total_sales_today: totalSalesToday,
      items_in_stock: itemsInStock,
      outstanding_bills: outstandingBills,
      net_profit_mtd: netProfitMtd,
    };
  }, [
    salesQuery.data,
    productsQuery.data,
    accountingKpiQuery.data,
    expensesQuery.data,
  ]);

  const salesSource = salesQuery.data?.source;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="bg-white border rounded-xl p-6">
        <h1 className="text-2xl font-semibold text-gray-900">Admin Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">
          Overview of operations, finance, and system activity
        </p>
        <p className="text-xs text-gray-400 mt-2">
          Sales Today uses POS Daily Sales ({asOfDate}) with fallback to sales list if the report route is missing.
          Outstanding Bills sums CREDIT expenses (payables exposure).
        </p>
        {salesSource ? (
          <p className="text-[11px] text-gray-400 mt-1">
            Sales Today source: <span className="font-mono">{salesSource}</span>
          </p>
        ) : null}
      </div>

      {/* KPI Cards */}
      <AdminKpiCards kpis={kpis} isLoading={isLoading} errorMessage={errorMessage} />

      {/* Quick Actions */}
      <AdminQuickActions />

      {/* Nested Pages */}
      <div className="bg-white border rounded-xl p-6">
        <Outlet />
      </div>
    </div>
  );
}
