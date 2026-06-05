// src/pages/AddProduct.jsx
import { useState } from "react";
import { apiClient } from "../lib/apiClient";

export default function AddProduct() {
  const [form, setForm] = useState({
    name: "",
    price: "",
    stock: "",
    barcode: "",
    expiry_date: "",
  });

  const update = (e) =>
    setForm({ ...form, [e.target.name]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    try {
      await apiClient("/products/create/", {
        method: "POST",
        body: JSON.stringify(form),
      });
      alert("Product added successfully.");
      setForm({
        name: "",
        price: "",
        stock: "",
        barcode: "",
        expiry_date: "",
      });
    } catch (err) {
      alert("Failed to save product.");
    }
  };

  return (
    <div className="p-6 max-w-xl mx-auto">
      <h1 className="text-xl font-bold mb-4">Add New Product</h1>

      <form className="space-y-4" onSubmit={submit}>
        <input
          name="name"
          className="w-full border p-2 rounded"
          placeholder="Product Name"
          value={form.name}
          onChange={update}
        />

        <input
          name="price"
          className="w-full border p-2 rounded"
          placeholder="Price"
          value={form.price}
          onChange={update}
        />

        <input
          name="stock"
          className="w-full border p-2 rounded"
          placeholder="Stock Quantity"
          value={form.stock}
          onChange={update}
        />

        <input
          name="barcode"
          className="w-full border p-2 rounded"
          placeholder="Barcode"
          value={form.barcode}
          onChange={update}
        />

        <input
          name="expiry_date"
          type="date"
          className="w-full border p-2 rounded"
          value={form.expiry_date}
          onChange={update}
        />

        <button className="bg-green-600 text-white px-4 py-2 rounded w-full">
          Save Product
        </button>
      </form>
    </div>
  );
}
