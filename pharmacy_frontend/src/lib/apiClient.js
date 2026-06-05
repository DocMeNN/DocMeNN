// src/lib/apiClient.js

import { API_BASE_URL } from "./config";
import {
  getAccessToken,
  getRefreshToken,
  saveTokens,
  clearTokens,
} from "./auth";

// Refresh access token using refresh token
async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  try {
    const response = await fetch(`${API_BASE_URL}/auth/jwt/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });

    if (!response.ok) return null;

    const data = await response.json();
    saveTokens(data.access, refresh); // reuse existing refresh
    return data.access;
  } catch (err) {
    console.error("Token refresh failed:", err);
    return null;
  }
}

// MAIN API CLIENT
export async function apiClient(endpoint, options = {}) {
  let token = getAccessToken();

  const headers = {
    "Content-Type": "application/json",
    ...(token && { Authorization: `Bearer ${token}` }),
    ...options.headers,
  };

  // first attempt
  let response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  // Unauthorized → try refresh
  if (response.status === 401) {
    const newToken = await refreshAccessToken();

    if (newToken) {
      // retry with new token
      response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        headers: {
          ...headers,
          Authorization: `Bearer ${newToken}`,
        },
      });
    } else {
      // logout user
      clearTokens();
      window.location.href = "/login";
      return;
    }
  }

  let data;

  try {
    data = await response.json();
  } catch {
    data = {};
  }

  if (!response.ok) {
    throw new Error(data.detail || "API Error");
  }

  return data;
}
