/**
 * ======================================================
 * PATH: src/lib/config.js
 * ======================================================
 *
 * FRONTEND ENV CONFIG
 * - Single source of truth for API base URL
 * - Supports local + Render via Vite env vars
 * - Avoids hardcoding localhost in production builds
 * ======================================================
 */

// Prefer Vite env vars (Render-friendly), fallback to localhost for dev
const API_HOST =
  import.meta?.env?.VITE_API_HOST?.trim() ||
  import.meta?.env?.VITE_API_BASE_URL?.trim() || // backward compat
  "http://127.0.0.1:8000";

const API_PREFIX = import.meta?.env?.VITE_API_PREFIX?.trim() || "/api";

// Normalize join (avoid double slashes)
function joinUrl(host, prefix) {
  const h = String(host || "").replace(/\/+$/, "");
  const p = String(prefix || "").trim();
  if (!p) return h;
  const pp = p.startsWith("/") ? p : `/${p}`;
  return `${h}${pp}`;
}

// 🔗 Base URL for your Django REST API
export const API_BASE_URL = joinUrl(API_HOST, API_PREFIX);
