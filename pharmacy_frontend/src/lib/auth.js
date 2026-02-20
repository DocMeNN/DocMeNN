// src/lib/auth.js
/**
 * ======================================================
 * PATH: src/lib/auth.js
 * ======================================================
 *
 * JWT TOKEN STORAGE + HELPERS
 * - Single source of truth for token keys
 * - Safe JWT decode (base64url)
 * ======================================================
 */

// Where we store JWT tokens (single standard across the app)
const ACCESS_KEY = "accessToken";
const REFRESH_KEY = "refreshToken";

// Save tokens to localStorage
export function saveTokens(access, refresh) {
  if (access) localStorage.setItem(ACCESS_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
}

// Get Access Token
export function getAccessToken() {
  return localStorage.getItem(ACCESS_KEY);
}

// Get Refresh Token
export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY);
}

// Remove tokens (logout)
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

// base64url decode helper (JWT uses base64url, not plain base64)
function base64UrlDecode(str) {
  const s = String(str || "").replace(/-/g, "+").replace(/_/g, "/");
  const pad = s.length % 4 ? "=".repeat(4 - (s.length % 4)) : "";
  return atob(s + pad);
}

// Decode JWT to get payload (role, email, id)
export function decodeJWT(token) {
  try {
    if (!token) return null;
    const parts = token.split(".");
    if (parts.length < 2) return null;

    const payload = parts[1];
    return JSON.parse(base64UrlDecode(payload));
  } catch {
    return null;
  }
}

// Get user information from token (best-effort; backend /me is authority)
export function getUserFromToken() {
  const access = getAccessToken();
  if (!access) return null;
  return decodeJWT(access);
}

// Check if user is authenticated (token exists; not a validity guarantee)
export function isLoggedIn() {
  return Boolean(getAccessToken());
}

// Check if user has a role (Admin, Cashier, Pharmacist, Reception)
export function hasRole(role) {
  const user = getUserFromToken();
  return user?.role === role;
}