// src/api/products.api.js

import axiosClient from "./axiosClient";

// --------------------------------------
// 📦 Fetch all products
// --------------------------------------
export async function getProducts() {
  const response = await axiosClient.get("/products/");
  return response.data;
}
