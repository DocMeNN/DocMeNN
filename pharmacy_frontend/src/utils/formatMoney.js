// src/utils/formatMoney.js

/**
 * Formats numeric values for display.
 * Currency symbol is intentionally NOT hard-coded.
 * This allows future support for:
 * - multiple currencies
 * - locale-based formatting
 * - tenant-level configuration
 */
export function formatMoney(value, options = {}) {
  const {
    locale = "en-NG",
    minimumFractionDigits = 0,
    maximumFractionDigits = 0,
  } = options;

  const number = Number(value || 0);

  return number.toLocaleString(locale, {
    minimumFractionDigits,
    maximumFractionDigits,
  });
}
