// src/routes/AppRoutes.jsx
/**
 * ======================================================
 * PATH: src/routes/AppRoutes.jsx
 * ======================================================
 *
 * AppRoutes (Routing Map)
 * ------------------------------------------------------
 * - Public storefront routes (AllowAny) under /store/:storeId/...
 * - Protected staff ERP routes under DashboardLayout
 * - Staff POS supports optional storeId in route: /pos/:storeId
 * - Receipt routes:
 *    - Public: /store/:storeId/receipt/:saleId
 *    - Staff:  /pos/:storeId/receipt/:saleId
 *
 * Phase 4 Paystack-safe flow:
 * - /store/:storeId/checkout   -> creates OnlineOrder + redirects to Paystack
 * - /store/:storeId/order/:orderId -> polling bridge, waits for sale_id then redirects to receipt
 * ======================================================
 */

import { useMemo, useState } from "react";
import {
  Routes,
  Route,
  Navigate,
  Outlet,
  useParams,
  useNavigate,
  Link,
} from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import ProtectedRoute from "./ProtectedRoute";

/* =======================
   AUTH
======================= */
import Login from "../features/auth/Login";
import Unauthorized from "../features/auth/Unauthorized";

/* =======================
   DASHBOARDS
======================= */
import AdminDashboard from "../features/admin/AdminDashboard";
import PharmacistDashboard from "../features/pharmacist/PharmacistDashboard";
import CashierDashboard from "../features/cashier/CashierDashboard";

function ReceptionDashboard() {
  return (
    <div className="bg-white border rounded-xl p-6">
      <h2 className="text-2xl font-semibold">Reception</h2>
      <p className="text-sm text-gray-600 mt-1">
        Reception dashboard is not wired yet.
      </p>
    </div>
  );
}

/* =======================
   OPERATIONS
======================= */
import InventoryPage from "../pages/InventoryPage";
import SalesHistory from "../features/sales/SalesHistory";
import PosPage from "../pages/PosPage";

/* ✅ STAFF POS RECEIPT */
import PosReceiptPage from "../pages/PosReceiptPage";

/* ✅ INVENTORY ALERTS (NEW UX) */
import ExpiryAlertsPage from "../features/inventory/ExpiryAlertsPage";

function ExpiryAlertsRoute() {
  const { storeId } = useParams();
  return <ExpiryAlertsPage storeId={storeId} />;
}

/* =======================
   ACCOUNTING PAGES
======================= */
import AccountingOverviewPage from "../pages/AccountingOverviewPage";
import TrialBalancePage from "../pages/TrialBalancePage";
import ProfitAndLossPage from "../pages/ProfitAndLossPage";
import BalanceSheetPage from "../pages/BalanceSheetPage";
import ExpensesPage from "../pages/ExpensesPage";
import ClosePeriodPage from "../pages/ClosePeriodPage";
import OpeningBalancesPage from "../pages/OpeningBalancesPage";

/* ✅ POS REPORTS */
import PosReportsPage from "../pages/PosReportsPage";

/* ✅ PUBLIC PAGES */
import StorePickerPage from "../pages/StorePickerPage";
import ShopPage from "../pages/ShopPage";
import StoreCartPage from "../pages/StoreCartPage";
import StoreReceiptPage from "../pages/StoreReceiptPage";

/* ✅ PHASE 4: ORDER STATUS (POLLING BRIDGE) */
import StoreOrderStatusPage from "../pages/StoreOrderStatusPage";

/* =======================
   LAYOUTS
======================= */
import DashboardLayout from "../layouts/DashboardLayout";
import AuthLayout from "../layouts/AuthLayout";
import AccountingLayout from "../layouts/AccountingLayout";
import CustomerLayout from "../layouts/CustomerLayout";

/* =======================
   PUBLIC CHECKOUT SUPPORT
======================= */
import { publicOrderInitiate } from "../features/pos/pos.api";
import {
  readPublicCart,
  computePublicCartSubtotal,
  countPublicCartItems,
} from "../lib/publicCart";
import { formatMoney } from "../utils/money";

/* =======================
   ROLE REDIRECT (STAFF)
======================= */
function RoleRedirect() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;

  switch (user.role) {
    case "admin":
      return <Navigate to="/dashboard/admin" replace />;
    case "pharmacist":
      return <Navigate to="/dashboard/pharmacist" replace />;
    case "cashier":
      return <Navigate to="/dashboard/cashier" replace />;
    case "reception":
      return <Navigate to="/dashboard/reception" replace />;
    default:
      return <Navigate to="/unauthorized" replace />;
  }
}

/* ======================================================
   PUBLIC ONLINE STORE (STORE-SCOPED)
====================================================== */

function StoreShell() {
  return <Outlet />;
}

function StoreHome() {
  const { storeId } = useParams();

  return (
    <div className="max-w-5xl mx-auto p-6">
      <div className="rounded-2xl border bg-white p-6">
        <h1 className="text-2xl font-semibold">Storefront</h1>
        <p className="text-gray-600 mt-2">
          Store ID: <span className="font-mono text-gray-800">{storeId}</span>
        </p>

        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            className="rounded-md bg-gray-900 px-4 py-2 text-white hover:bg-gray-800"
            to={`/store/${storeId}/shop`}
          >
            Browse Products
          </Link>

          <Link
            className="rounded-md border px-4 py-2 hover:bg-gray-50"
            to={`/store/${storeId}/cart`}
          >
            View Cart
          </Link>
        </div>
      </div>
    </div>
  );
}

function StoreCheckout() {
  const { storeId } = useParams();

  const [customer_name, setName] = useState("");
  const [customer_phone, setPhone] = useState("");
  const [customer_email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState("");

  const itemCount = useMemo(() => countPublicCartItems(storeId), [storeId]);
  const subtotal = useMemo(() => computePublicCartSubtotal(storeId), [storeId]);

  const cart = useMemo(() => readPublicCart(storeId), [storeId]);
  const items = Array.isArray(cart?.items) ? cart.items : [];

  function buildInitiatePayload() {
    const safeStoreId = String(storeId || "").trim();
    const lines = items.map((it) => ({
      product_id: it.product_id,
      quantity: Number(it.quantity || 0),
    }));

    return {
      store_id: safeStoreId,
      customer_name: String(customer_name || "").trim() || undefined,
      customer_phone: String(customer_phone || "").trim() || undefined,
      customer_email: String(customer_email || "").trim() || undefined,
      items: lines,
    };
  }

  async function handleCheckout() {
    setErr("");
    setStatus("");

    const safeStoreId = String(storeId || "").trim();
    if (!safeStoreId) return setErr("Store not selected.");
    if (items.length === 0) return setErr("Your cart is empty.");

    const payload = buildInitiatePayload();
    if (!payload.items.length) return setErr("Your cart is empty.");

    setSubmitting(true);
    try {
      // ✅ PHASE 4: initiate safe order + payment
      const res = await publicOrderInitiate(payload);

      const authorizationUrl = String(res?.authorization_url || "").trim();
      if (!authorizationUrl) {
        throw new Error("Payment initiated but authorization_url is missing.");
      }

      // Important: do NOT clear the public cart here. Clear ONLY after sale is finalized.
      // Webhook might fail; we want customer to retry without losing cart.

      setStatus("Redirecting to payment…");
      window.location.href = authorizationUrl;
    } catch (e) {
      setErr(e?.message || "Checkout failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      <div className="rounded-2xl border bg-white p-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-2xl font-semibold">Checkout</h2>
            <p className="text-gray-600 mt-1">
              Store: <span className="font-mono">{storeId}</span>
            </p>
          </div>

          <Link
            to={`/store/${storeId}/cart`}
            className="px-4 py-2 rounded-md border hover:bg-gray-50"
          >
            Back to cart
          </Link>
        </div>

        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-gray-700">
              Customer name (optional)
            </label>
            <input
              className="mt-1 w-full border rounded-md px-3 py-2"
              value={customer_name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Jane Doe"
              autoComplete="name"
            />
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700">
              Phone (optional)
            </label>
            <input
              className="mt-1 w-full border rounded-md px-3 py-2"
              value={customer_phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="080..."
              autoComplete="tel"
            />
          </div>

          <div className="md:col-span-2">
            <label className="text-sm font-medium text-gray-700">
              Email (optional)
            </label>
            <input
              className="mt-1 w-full border rounded-md px-3 py-2"
              value={customer_email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="jane@example.com"
              autoComplete="email"
            />
          </div>
        </div>

        {(err || status) && (
          <div
            className={`mt-5 border rounded p-3 text-sm ${
              err
                ? "border-red-200 bg-red-50 text-red-800"
                : "border-green-200 bg-green-50 text-green-800"
            }`}
          >
            {err || status}
          </div>
        )}
      </div>

      <div className="rounded-2xl border bg-white">
        <div className="p-4 border-b flex items-center justify-between">
          <div className="font-semibold">Order summary</div>
          <div className="text-sm text-gray-600">
            {itemCount} item{itemCount === 1 ? "" : "s"}
          </div>
        </div>

        {items.length === 0 ? (
          <div className="p-6 text-gray-600">
            Your cart is empty.{" "}
            <Link to={`/store/${storeId}/shop`} className="underline">
              Browse products
            </Link>
          </div>
        ) : (
          <div className="p-4 space-y-3">
            {items.map((it) => (
              <div
                key={it.product_id}
                className="border rounded-xl p-4 flex items-start justify-between gap-4 flex-wrap"
              >
                <div className="min-w-[240px]">
                  <div className="font-semibold text-gray-900">{it.name}</div>
                  {it.sku ? (
                    <div className="text-xs text-gray-500 mt-1">
                      SKU: <span className="font-mono">{it.sku}</span>
                    </div>
                  ) : null}
                </div>

                <div className="text-sm text-gray-700">
                  {Number(it.quantity || 0)} × {formatMoney(it.unit_price)}
                </div>

                <div className="font-semibold">
                  {formatMoney(
                    Number(it.unit_price || 0) * Number(it.quantity || 0)
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="p-5 border-t flex items-center justify-between gap-4 flex-wrap">
          <div>
            <div className="text-sm text-gray-600">Subtotal</div>
            <div className="text-2xl font-bold">{formatMoney(subtotal)}</div>
            <div className="text-xs text-gray-500 mt-1">
              Final stock + totals are validated by backend after verified payment.
            </div>
          </div>

          <button
            type="button"
            onClick={handleCheckout}
            disabled={submitting || items.length === 0}
            className="px-5 py-3 rounded-md bg-gray-900 text-white hover:bg-gray-800 disabled:opacity-50"
          >
            {submitting ? "Processing…" : "Pay with Card"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AppRoutes() {
  return (
    <Routes>
      {/* PUBLIC ONLINE STORE */}
      <Route path="/store" element={<CustomerLayout />}>
        <Route index element={<StorePickerPage />} />
      </Route>

      <Route path="/store/:storeId" element={<CustomerLayout />}>
        <Route element={<StoreShell />}>
          <Route index element={<StoreHome />} />
          <Route path="shop" element={<ShopPage />} />
          <Route path="cart" element={<StoreCartPage />} />
          <Route path="checkout" element={<StoreCheckout />} />

          {/* ✅ PHASE 4: polling bridge */}
          <Route path="order/:orderId" element={<StoreOrderStatusPage />} />

          <Route path="receipt/:saleId" element={<StoreReceiptPage />} />
        </Route>
      </Route>

      {/* AUTH */}
      <Route
        path="/login"
        element={
          <AuthLayout>
            <Login />
          </AuthLayout>
        }
      />

      <Route path="/unauthorized" element={<Unauthorized />} />
      <Route path="/" element={<RoleRedirect />} />

      {/* PROTECTED ERP APP */}
      <Route
        element={
          <ProtectedRoute allowedRoles={["admin", "pharmacist", "cashier", "reception"]}>
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        {/* DASHBOARDS */}
        <Route path="dashboard/admin" element={<AdminDashboard />} />
        <Route path="dashboard/pharmacist" element={<PharmacistDashboard />} />
        <Route path="dashboard/cashier" element={<CashierDashboard />} />
        <Route path="dashboard/reception" element={<ReceptionDashboard />} />

        {/* ✅ OPERATIONS */}
        <Route path="inventory" element={<InventoryPage />} />
        <Route
          path="inventory/expiry-alerts"
          element={
            <ProtectedRoute allowedRoles={["admin", "pharmacist"]}>
              <ExpiryAlertsRoute />
            </ProtectedRoute>
          }
        />
        <Route
          path="inventory/expiry-alerts/:storeId"
          element={
            <ProtectedRoute allowedRoles={["admin", "pharmacist"]}>
              <ExpiryAlertsRoute />
            </ProtectedRoute>
          }
        />

        <Route path="sales" element={<SalesHistory />} />

        {/* POS */}
        <Route path="pos" element={<PosPage />} />
        <Route path="pos/:storeId" element={<PosPage />} />
        <Route path="pos/:storeId/receipt/:saleId" element={<PosReceiptPage />} />

        {/* ACCOUNTING */}
        <Route path="accounting" element={<AccountingLayout />}>
          <Route index element={<AccountingOverviewPage />} />
          <Route path="trial-balance" element={<TrialBalancePage />} />
          <Route path="profit-and-loss" element={<ProfitAndLossPage />} />
          <Route path="balance-sheet" element={<BalanceSheetPage />} />

          <Route
            path="opening-balances"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <OpeningBalancesPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="expenses"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <ExpensesPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="close-period"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <ClosePeriodPage />
              </ProtectedRoute>
            }
          />

          <Route
            path="pos-reports"
            element={
              <ProtectedRoute allowedRoles={["admin"]}>
                <PosReportsPage />
              </ProtectedRoute>
            }
          />
        </Route>
      </Route>

      {/* FALLBACK */}
      <Route path="*" element={<Navigate to="/store" replace />} />
    </Routes>
  );
}