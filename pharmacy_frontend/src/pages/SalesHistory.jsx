// src/pages/SalesHistory.jsx

import { useAuth } from "../context/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../lib/apiClient";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

export default function SalesHistory() {
  const { user } = useAuth();

  const { data, isLoading, error } = useQuery({
    queryKey: ["sales-history"],
    queryFn: () => apiClient("/sales/"),
  });

  if (isLoading) return <p className="p-4">Loading sales...</p>;
  if (error) return <p className="p-4">Failed to load sales.</p>;

  const sales = data || [];

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Sales History</h1>
      <p className="text-gray-600">User: {user?.username} ({user?.role})</p>

      <Card>
        <CardHeader>
          <CardTitle>All Sales Records</CardTitle>
        </CardHeader>

        <CardContent>
          <div className="space-y-4">
            {sales.map((sale) => (
              <Card key={sale.id} className="border-l-4 border-blue-600">
                <CardContent className="p-4">
                  <p className="font-semibold text-lg">
                    Sale #{sale.id} - ₦{sale.total}
                  </p>
                  <p className="text-sm text-gray-600">
                    Date: {new Date(sale.created_at).toLocaleString()}
                  </p>

                  <ul className="mt-2 text-sm">
                    {sale.items.map((item) => (
                      <li key={item.id}>
                        {item.product_name} — {item.quantity} × ₦{item.price}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            ))}

            {sales.length === 0 && (
              <p className="text-gray-500 text-center py-6">No sales found.</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
