// src/pages/SalesHistory.jsx

import { useAuth } from "../context/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../lib/apiClient";
import { formatMoney } from "../utils/money";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

export default function SalesHistory() {
  const { user } = useAuth();

  const { data, isLoading, error } = useQuery({
    queryKey: ["sales-history"],
    // ✅ Correct endpoint: staff sales list lives here
    queryFn: () => apiClient("/sales/sales/"),
  });

  if (isLoading) return <p className="p-6">Loading sales...</p>;

  if (error) {
    return (
      <div className="p-6 space-y-2">
        <p className="font-semibold text-red-600">Failed to load sales history.</p>
        <p className="text-sm text-gray-600">
          Tip: Open DevTools → Network, confirm request hits{" "}
          <span className="font-mono">/api/sales/sales/</span> and returns 200.
        </p>
      </div>
    );
  }

  // DRF pagination-safe
  const sales = data?.results || data || [];

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Sales History</h1>

      <p className="text-gray-600">
        User: {user?.username} ({user?.role})
      </p>

      {!Array.isArray(sales) || sales.length === 0 ? (
        <p className="text-gray-500">No sales recorded.</p>
      ) : (
        <div className="space-y-4">
          {sales.map((sale) => {
            const items = Array.isArray(sale?.items) ? sale.items : [];

            return (
              <Card key={sale.id} className="border-l-4 border-blue-600">
                <CardHeader>
                  <CardTitle className="flex justify-between items-center">
                    <span>Invoice #{sale.invoice_no || "—"}</span>
                    <span className="text-sm text-gray-600">
                      {formatMoney(sale.total_amount)}
                    </span>
                  </CardTitle>
                </CardHeader>

                <CardContent className="space-y-2">
                  <p className="text-sm text-gray-600">
                    Date:{" "}
                    {sale.created_at ? new Date(sale.created_at).toLocaleString() : "—"}
                  </p>

                  <p className="text-sm">
                    Status:{" "}
                    <span className="font-medium capitalize">{sale.status || "—"}</span>
                  </p>

                  {/* Items may or may not be included depending on backend list serializer */}
                  <div className="mt-3">
                    <p className="font-semibold text-sm mb-1">Items</p>

                    {items.length === 0 ? (
                      <p className="text-sm text-gray-500">
                        Items not included in list response.
                      </p>
                    ) : (
                      <ul className="text-sm space-y-1">
                        {items.map((item) => (
                          <li key={item.id}>
                            {item.product_name || "Item"} — {item.quantity} ×{" "}
                            {formatMoney(item.unit_price)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <div className="border-t pt-2 text-sm space-y-1">
                    <p>Subtotal: {formatMoney(sale.subtotal_amount)}</p>
                    <p>Tax: {formatMoney(sale.tax_amount)}</p>
                    <p>Discount: {formatMoney(sale.discount_amount)}</p>
                    <p className="font-semibold">
                      Total: {formatMoney(sale.total_amount)}
                    </p>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
