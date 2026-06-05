import { useState } from "react";

export default function ProductDetails({ product, addToCart }) {
  const [qty, setQty] = useState(1);

  if (!product) {
    return (
      <div className="bg-white rounded shadow p-4 text-gray-500">
        Select a product to view details
      </div>
    );
  }

  return (
    <div className="bg-white rounded shadow p-4">
      <h2 className="text-xl font-semibold mb-2">{product.name}</h2>
      <p className="text-lg font-bold">₦{product.price}</p>

      <div className="my-4">
        <label className="block mb-1">Quantity</label>
        <input
          type="number"
          min="1"
          value={qty}
          onChange={(e) => setQty(Number(e.target.value))}
          className="w-20 p-2 border rounded"
        />
      </div>

      <button
        onClick={() => addToCart(product, qty)}
        className="px-4 py-2 bg-blue-600 text-white rounded"
      >
        Add to Cart
      </button>
    </div>
  );
}
