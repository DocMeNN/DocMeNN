// src/lib/apiClient.js

import { API_BASE_URL } from "./config";
import {
  getAccessToken,
  getRefreshToken,
  saveTokens,
  clearTokens,
} from "./auth";

/**
 * Refresh access token using refresh token
 * Returns new access token or null on failure
 */
async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  try {
    const response = await fetch(`${API_BASE_URL}/auth/jwt/refresh/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh }),
    });

    if (!response.ok) return null;

    const data = await response.json();

    if (!data?.access) return null;

    // Persist new access token, reuse existing refresh token
    saveTokens(data.access, refresh);

    return data.access;
  } catch (err) {
    console.error("Token refresh failed:", err);
    return null;
  }
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

  // ---------- FIRST REQUEST ----------
  const initialHeaders = {
    "Content-Type": "application/json",
    ...options.headers,
    ...(accessToken && { Authorization: `Bearer ${accessToken}` }),
  };

  let response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: initialHeaders,
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
    const retryHeaders = {
      "Content-Type": "application/json",
      ...options.headers,
      Authorization: `Bearer ${newAccessToken}`,
    };

    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: retryHeaders,
    });
  }

  // ---------- PARSE RESPONSE ----------
  let data = {};

  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    throw new Error(data?.detail || "API Error");
  }

  return data;
}
