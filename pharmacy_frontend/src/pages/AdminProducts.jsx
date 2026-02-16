// src/pages/AdminProducts.jsx

import { useEffect, useState } from "react";
import { getProducts } from "../api/products.api";
import { formatMoney } from "../utils/money";

function formatOptionalMoney(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "—";
  return formatMoney(n);
}

export default function AdminProducts() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadProducts() {
      try {
        const data = await getProducts();
        setProducts(data);
      } catch {
        setError("Failed to load products");
      } finally {
        setLoading(false);
      }
    }
    loadProducts();
  }, []);

  if (loading) return <p className="p-6">Loading products...</p>;
  if (error) return <p className="p-6 text-red-600">{error}</p>;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Products</h1>

      {products.length === 0 ? (
        <p>No products found.</p>
      ) : (
        <ul className="space-y-3">
          {products.map((product) => (
            <li
              key={product.id}
              className="border p-4 rounded flex justify-between items-center"
            >
              <div>
                <p className="font-semibold">{product.name}</p>
                <p className="text-sm text-gray-600">
                  {formatOptionalMoney(product.price)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
