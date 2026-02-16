// src/utils/moneyMath.js

export function toCents(value) {
  // Accept number or string; convert to integer cents safely
  const s = String(value ?? "").trim();
  if (!s) return 0;

  // Remove commas
  const normalized = s.replace(/,/g, "");

  // If it's already like "2500" treat as naira, not cents:
  // we'll parse as decimal naira and multiply by 100
  const n = Number(normalized);
  if (!Number.isFinite(n)) return 0;

  return Math.round(n * 100);
}

export function centsToAmountString(cents) {
  const v = Math.round(Number(cents || 0));
  const naira = (v / 100).toFixed(2);
  return naira;
}

export function sumCents(lines) {
  return (lines || []).reduce((acc, x) => acc + (Number(x?.amountCents) || 0), 0);
}
