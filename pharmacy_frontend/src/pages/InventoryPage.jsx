// src/pages/InventoryPage.jsx
import { useState, useEffect } from "react";
import { apiClient } from "../lib/apiClient";

export default function InventoryPage() {
  const [products, setProducts] = useState([]);
  const [search, setSearch] = useState("");

  // Load products
  useEffect(() => {
    async function load() {
      try {
        const data = await apiClient("/products/");
        setProducts(data);
      } catch (err) {
        alert("Failed to load inventory.");
      }
    }
    load();
  }, []);

  const filtered = products.filter((p) =>
    p.name.toLowerCase().includes(search.toLowerCase())
  );

  const deleteProduct = async (id) => {
    if (!window.confirm("Delete this product?")) return;

    try {
      await apiClient(`/products/${id}/delete/`, { method: "DELETE" });
      setProducts((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      alert("Failed to delete product.");
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-xl font-bold mb-4">Inventory Management</h1>

      {/* Search */}
      <input
        className="border px-3 py-2 rounded mb-4 w-64"
        placeholder="Search products..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {/* Product Table */}
      <table className="w-full border mt-3">
        <thead className="bg-gray-100">
          <tr>
            <th className="p-3 border">Name</th>
            <th className="p-3 border">Price</th>
            <th className="p-3 border">Stock</th>
            <th className="p-3 border">Expiry</th>
            <th className="p-3 border">Actions</th>
          </tr>
        </thead>

        <tbody>
          {filtered.map((p) => (
            <tr key={p.id} className="border">
              <td className="p-3 border">{p.name}</td>
              <td className="p-3 border">₦{p.price}</td>
              <td className="p-3 border">{p.stock}</td>
              <td className="p-3 border">
                {p.expiry_date || <span className="text-gray-400">N/A</span>}
              </td>
              <td className="p-3 border flex gap-2">
                <button className="bg-blue-600 text-white px-3 py-1 rounded">
                  Edit
                </button>
                <button
                  className="bg-red-600 text-white px-3 py-1 rounded"
                  onClick={() => deleteProduct(p.id)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
