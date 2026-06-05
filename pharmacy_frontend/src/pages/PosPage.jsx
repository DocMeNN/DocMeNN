import React, { useState, useEffect } from "react";
import { apiClient } from "../lib/apiClient";

export default function PosPage() {
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState([]);
  const [loading, setLoading] = useState(true);
  const [barcode, setBarcode] = useState("");

  // --------------------------------------
  // Load products
  // --------------------------------------
  useEffect(() => {
    async function loadProducts() {
      try {
        const data = await apiClient("/products/");
        setProducts(data);
      } catch (err) {
        console.error("Error loading products:", err);
        alert("Failed to load products from backend.");
      }
      setLoading(false);
    }

    loadProducts();
  }, []);

  // --------------------------------------
  // Add to cart (manual or barcode)
  // --------------------------------------
  const addToCart = (product) => {
    setCart((prev) => {
      const exists = prev.find((item) => item.id === product.id);
      if (exists) {
        return prev.map((item) =>
          item.id === product.id
            ? { ...item, quantity: item.quantity + 1 }
            : item
        );
      }
      return [...prev, { ...product, quantity: 1 }];
    });
  };

  // --------------------------------------
  // Scan barcode
  // --------------------------------------
  const handleBarcodeAdd = () => {
    if (!barcode.trim()) return;

    const found = products.find(
      (p) => String(p.barcode) === String(barcode.trim())
    );

    if (!found) {
      alert("No product with this barcode.");
      setBarcode("");
      return;
    }

    addToCart(found);
    setBarcode("");
  };

  // --------------------------------------
  // Change quantity
  // --------------------------------------
  const changeQuantity = (id, delta) => {
    setCart((prev) =>
      prev
        .map((item) =>
          item.id === id
            ? { ...item, quantity: Math.max(1, item.quantity + delta) }
            : item
        )
        .filter((item) => item.quantity > 0)
    );
  };

  // --------------------------------------
  // Remove item
  // --------------------------------------
  const removeItem = (id) => {
    setCart((prev) => prev.filter((item) => item.id !== id));
  };

  // --------------------------------------
  // Total
  // --------------------------------------
  const total = cart.reduce(
    (sum, item) => sum + Number(item.price) * item.quantity,
    0
  );

  // --------------------------------------
  // Checkout
  // --------------------------------------
  const handleCheckout = async () => {
    if (cart.length === 0) return alert("Cart is empty!");

    const salePayload = {
      items: cart.map((item) => ({
        product_id: item.id,
        quantity: item.quantity,
        price: item.price,
      })),
    };

    try {
      const data = await apiClient("/sales/create/", {
        method: "POST",
        body: JSON.stringify(salePayload),
      });

      alert("Sale complete! Sale ID: " + data.sale_id);
      setCart([]);
    } catch (error) {
      console.error("Checkout error:", error);
      alert("Failed to complete sale.");
    }
  };

  // --------------------------------------
  // UI Loading
  // --------------------------------------
  if (loading) return <p className="p-4">Loading products...</p>;

  return (
    <div className="p-6 space-y-6">

      <h1 className="text-2xl font-bold mb-4">Point of Sale (POS)</h1>

      {/* Barcode Section */}
      <div className="flex items-center gap-3 mb-6">
        <input
          type="text"
          className="border px-3 py-2 rounded w-64"
          placeholder="Scan or enter barcode..."
          value={barcode}
          onChange={(e) => setBarcode(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleBarcodeAdd()}
        />
        <button
          className="px-4 py-2 bg-green-600 text-white rounded"
          onClick={handleBarcodeAdd}
        >
          Add
        </button>
      </div>

      {/* Product List */}
      <div>
        <h2 className="text-lg font-bold mb-2">Products</h2>

        <div className="grid grid-cols-3 gap-4">
          {products.map((product) => (
            <div
              key={product.id}
              className="border p-4 rounded shadow cursor-pointer hover:bg-gray-100"
              onClick={() => addToCart(product)}
            >
              <h2 className="font-semibold">{product.name}</h2>
              <p className="text-sm text-gray-600">₦{product.price}</p>
              <p className="text-xs text-gray-500 mt-1">
                Barcode: {product.barcode || "N/A"}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Cart */}
      <div className="mt-6">
        <h2 className="text-lg font-bold mb-2">Cart</h2>

        {cart.length === 0 ? (
          <p className="text-gray-500">No items added</p>
        ) : (
          <div className="space-y-4">
            {cart.map((item) => (
              <div
                key={item.id}
                className="border p-4 rounded flex justify-between items-center"
              >
                <div>
                  <p className="font-semibold">{item.name}</p>
                  <p className="text-sm text-gray-600">
                    ₦{item.price} × {item.quantity}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    className="px-2 py-1 bg-gray-300 rounded"
                    onClick={() => changeQuantity(item.id, -1)}
                  >
                    -
                  </button>
                  <button
                    className="px-2 py-1 bg-gray-300 rounded"
                    onClick={() => changeQuantity(item.id, +1)}
                  >
                    +
                  </button>
                  <button
                    className="px-2 py-1 bg-red-500 text-white rounded"
                    onClick={() => removeItem(item.id)}
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Checkout */}
        <h3 className="text-lg font-bold mt-4">
          Total: ₦{total.toFixed(2)}
        </h3>

        <button
          onClick={handleCheckout}
          className="mt-4 bg-blue-600 text-white px-4 py-2 rounded"
        >
          Checkout
        </button>
      </div>
    </div>
  );
}
