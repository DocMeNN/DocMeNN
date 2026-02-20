/**
 * ======================================================
 * PATH: src/api/sales.api.js
 * ======================================================
 *
 * SALES API (COMPAT WRAPPER)
 * ------------------------------------------------------
 * Why this exists:
 * - Older parts of the UI may import from src/api/sales.api.js
 * - New canonical Sales API lives in src/features/sales/sales.api.js
 *
 * Rule:
 * - This file must NOT define endpoints independently.
 * - It delegates to the canonical module to prevent drift.
 * ======================================================
 */

import {
  fetchSales as listSales,
  fetchSaleById as getSaleById,
  refundSale as refundSaleById,
} from "../features/sales/sales.api";

// Backward compatible exports
export { listSales, getSaleById };

/**
 * Refund a completed sale
 * Signature kept flexible for older callers.
 */
export const refundSale = ({ saleId, reason, items } = {}) => {
  return refundSaleById(saleId, { reason, items });
};

// Legacy functions kept but intentionally not supported here
// because POS now uses /pos/cart + /pos/checkout orchestration.
// If you still need draft-sale style endpoints, we should build them
// in ONE place and wire UI accordingly (not guess).
export const createDraftSale = () => {
  throw new Error(
    "createDraftSale is deprecated. Use POS cart flow (/pos/cart + /pos/checkout)."
  );
};

export const addItemToSale = () => {
  throw new Error(
    "addItemToSale is deprecated. Use POS cart flow (/pos/cart/items/add/)."
  );
};

export const updateSaleItem = () => {
  throw new Error(
    "updateSaleItem is deprecated. Use POS cart flow (/pos/cart/items/:id/update/)."
  );
};

export const removeItemFromSale = () => {
  throw new Error(
    "removeItemFromSale is deprecated. Use POS cart flow (/pos/cart/items/:id/remove/)."
  );
};

export const completeSale = () => {
  throw new Error(
    "completeSale is deprecated. Use POS checkout flow (/pos/checkout/)."
  );
};
