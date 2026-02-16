// src/api/sales.api.js

import axiosClient from "./axiosClient";

/**
 * SALES API CONTRACT
 * ------------------
 * The backend is the single source of truth.
 * This file only sends commands and reads backend state.
 * No totals, no prices, no calculations.
 */

/**
 * Create a new draft sale
 * Backend decides initial state and totals
 */
export const createDraftSale = () => {
  return axiosClient.post("/sales/");
};

/**
 * Fetch a sale by ID
 * Used to render current truth (items, totals, status)
 */
export const getSaleById = (saleId) => {
  return axiosClient.get(`/sales/${saleId}/`);
};

/**
 * Add item to a draft sale
 * Backend updates quantities, totals, and stock validation
 */
export const addItemToSale = ({ saleId, productId, quantity = 1 }) => {
  return axiosClient.post(`/sales/${saleId}/items/`, {
    product_id: productId,
    quantity,
  });
};

/**
 * Update item quantity in a draft sale
 * Quantity rules are enforced by backend
 */
export const updateSaleItem = ({ saleId, itemId, quantity }) => {
  return axiosClient.patch(`/sales/${saleId}/items/${itemId}/`, {
    quantity,
  });
};

/**
 * Remove item from a draft sale
 */
export const removeItemFromSale = ({ saleId, itemId }) => {
  return axiosClient.delete(`/sales/${saleId}/items/${itemId}/`);
};

/**
 * Complete a sale
 * This commits stock and locks the sale
 */
export const completeSale = (saleId) => {
  return axiosClient.post(`/sales/${saleId}/complete/`);
};

/**
 * Refund a completed sale
 * Backend handles audit and stock restoration
 */
export const refundSale = ({ saleId, reason }) => {
  return axiosClient.post(`/sales/${saleId}/refund/`, {
    reason,
  });
};

/**
 * List sales (history)
 * Backend controls filtering and visibility
 */
export const listSales = () => {
  return axiosClient.get("/sales/");
};
