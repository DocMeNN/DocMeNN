// src/utils/money.js

/**
 * ======================================================
 * formatMoney
 * ------------------------------------------------------
 * Single source of truth for all monetary display
 *
 * Rules:
 * - No hard-coded symbols anywhere else in the app
 * - Always two decimal places (accounting grade)
 * - Safe for null / undefined / strings
 * - Handles negatives correctly
 * - Locale + currency locked centrally
 * ======================================================
 */

const LOCALE = "en-NG";
const CURRENCY = "NGN";

export function formatMoney(amount) {
  const value = Number(amount);

  // Defensive: handle NaN, null, undefined, empty
  const safeValue = Number.isFinite(value) ? value : 0;

  return new Intl.NumberFormat(LOCALE, {
    style: "currency",
    currency: CURRENCY,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(safeValue);
}
