/**
 * ======================================================
 * PATH: src/lib/apiClient.js
 * ======================================================
 *
 * MAIN API CLIENT (fetch-based)
 * - Attaches access token (Bearer)
 * - Auto-refreshes on 401 (single retry)
 * - Safely handles JSON + non-JSON + 204 responses
 * - Avoids forcing Content-Type when using FormData
 *
 * NOTE:
 * - This is legacy in a codebase that mostly uses axiosClient.js.
 * - Keeping it working is fine, but prefer axiosClient for app APIs.
 * ======================================================
 */

import { API_BASE_URL } from "./config";
import { getAccessToken, getRefreshToken, saveTokens, clearTokens } from "./auth";

/**
 * Join base + path safely without double slashes.
 */
function joinUrl(base, path) {
  const b = String(base || "").replace(/\/+$/, "");
  const p = String(path || "");
  const normalizedPath = p.startsWith("/") ? p : `/${p}`;
  return `${b}${normalizedPath}`;
}

/**
 * Only set JSON Content-Type when appropriate:
 * - body exists
 * - body is NOT FormData
 * - caller hasn't already set Content-Type
 */
function buildHeaders(optionsHeaders, accessToken, body) {
  const headers = {
    ...optionsHeaders,
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };

  const hasContentType = Object.keys(headers).some(
    (k) => k.toLowerCase() === "content-type"
  );

  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

  if (!hasContentType && body != null && !isFormData) {
    headers["Content-Type"] = "application/json";
  }

  return headers;
}

/**
 * Refresh access token using refresh token
 * Returns new access token or null on failure
 */
async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  try {
    const url = joinUrl(API_BASE_URL, "/auth/jwt/refresh/");

    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });

    if (!response.ok) return null;

    const data = await response.json().catch(() => null);
    if (!data?.access) return null;

    // Persist new access token, reuse existing refresh token
    saveTokens(data.access, refresh);

    return data.access;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("Token refresh failed:", err);
    return null;
  }
}

/**
 * Parse response:
 * - 204 -> {}
 * - JSON -> object
 * - non-JSON -> { raw: text }
 */
async function parseResponse(response) {
  if (response.status === 204) return {};

  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");

  if (isJson) {
    return await response.json().catch(() => ({}));
  }

  const text = await response.text().catch(() => "");
  return text ? { raw: text } : {};
}

/**
 * MAIN API CLIENT
 * - Attaches access token
 * - Auto-refreshes on 401
 * - Retries once
 * - Forces logout on hard auth failure
 */
export async function apiClient(endpoint, options = {}) {
  const accessToken = getAccessToken();
  const method = String(options.method || "GET").toUpperCase();

  const body = options.body ?? null;

  // If caller provided a plain object body and did not provide Content-Type,
  // we will stringify it.
  const headersLower = Object.keys(options.headers || {}).reduce((acc, k) => {
    acc[k.toLowerCase()] = true;
    return acc;
  }, {});

  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;
  const isJsonBodyCandidate =
    body != null && !isFormData && typeof body === "object" && !Array.isArray(body);

  const finalBody =
    isJsonBodyCandidate && !headersLower["content-type"] ? JSON.stringify(body) : body;

  // ---------- FIRST REQUEST ----------
  const initialHeaders = buildHeaders(options.headers || {}, accessToken, finalBody);

  let response = await fetch(joinUrl(API_BASE_URL, endpoint), {
    ...options,
    method,
    headers: initialHeaders,
    body: finalBody,
  });

  // ---------- HANDLE UNAUTHORIZED ----------
  if (response.status === 401) {
    const newAccessToken = await refreshAccessToken();

    if (!newAccessToken) {
      // Hard auth failure → logout
      clearTokens();
      window.location.href = "/login";
      return;
    }

    // ---------- RETRY WITH FRESH TOKEN ----------
    const retryHeaders = buildHeaders(options.headers || {}, newAccessToken, finalBody);

    response = await fetch(joinUrl(API_BASE_URL, endpoint), {
      ...options,
      method,
      headers: retryHeaders,
      body: finalBody,
    });
  }

  // ---------- PARSE RESPONSE ----------
  const data = await parseResponse(response);

  if (!response.ok) {
    // Try DRF-style detail, then fallback
    const msg =
      (typeof data?.detail === "string" && data.detail) ||
      (typeof data?.message === "string" && data.message) ||
      "API Error";
    throw new Error(msg);
  }

  return data;
}
