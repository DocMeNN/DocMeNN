// src/api/axiosClient.js

import axios from "axios";

/**
 * ======================================================
 * AXIOS CLIENT — SINGLE SOURCE OF NETWORK TRUTH
 * ------------------------------------------------------
 * Responsibilities:
 * - Attach auth tokens
 * - Enforce consistent headers
 * - Handle global auth failures
 * - Token refresh (single-flight, retry once)
 * - NEVER hide errors
 * ======================================================
 */

// Base host (no /api here)
const API_HOST =
  import.meta?.env?.VITE_API_HOST?.trim() ||
  import.meta?.env?.VITE_API_BASE_URL?.trim() || // backward compatible
  "http://127.0.0.1:8000";

// API prefix (default /api)
const API_PREFIX =
  import.meta?.env?.VITE_API_PREFIX?.trim() || "/api";

// Normalize join (avoid double slashes)
function joinUrl(host, prefix) {
  const h = String(host || "").replace(/\/+$/, "");
  const p = String(prefix || "").trim();
  if (!p) return h;
  const pp = p.startsWith("/") ? p : `/${p}`;
  return `${h}${pp}`;
}

// ✅ This is what all relative calls will hit
const baseURL = joinUrl(API_HOST, API_PREFIX);

const axiosClient = axios.create({
  baseURL,
  timeout: 15000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

/** -----------------------------
 * Token helpers
 * ----------------------------- */
function getAccessToken() {
  return localStorage.getItem("access_token");
}
function getRefreshToken() {
  return localStorage.getItem("refresh_token");
}
function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
}
function setTokens({ access, refresh }) {
  if (access) localStorage.setItem("access_token", access);
  if (refresh) localStorage.setItem("refresh_token", refresh);
}

/** -----------------------------
 * Request Interceptor
 * ----------------------------- */
axiosClient.interceptors.request.use(
  (config) => {
    const token = getAccessToken();
    const url = config?.url || "";

    const isAnonymousAuthEndpoint =
      url.includes("/auth/jwt/create/") || url.includes("/auth/jwt/refresh/");

    if (token && !isAnonymousAuthEndpoint) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

/** -----------------------------
 * Response Interceptor (401 refresh)
 * ----------------------------- */
let isRefreshing = false;
let refreshQueue = [];

function subscribeTokenRefresh(cb) {
  refreshQueue.push(cb);
}
function notifyTokenRefreshed(newAccessToken) {
  refreshQueue.forEach((cb) => cb(newAccessToken));
  refreshQueue = [];
}

async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) throw new Error("No refresh token available");

  // IMPORTANT: use a plain axios instance to avoid recursion through interceptors
  // Use SAME baseURL (includes /api) because auth routes typically live under /api/auth/...
  const res = await axios.post(
    `${baseURL}/auth/jwt/refresh/`,
    { refresh },
    {
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      timeout: 15000,
    }
  );

  const access = res?.data?.access;
  if (!access) throw new Error("Token refresh failed");

  setTokens({ access });
  return access;
}

axiosClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    // No response = server down, DNS, wrong URL, CORS, blocked request
    if (!error?.response) {
      const normalized = new Error(
        `Network error: backend not reachable (or blocked by CORS). baseURL=${baseURL}`
      );
      normalized.cause = error;
      return Promise.reject(normalized);
    }

    const status = error?.response?.status;
    const originalRequest = error?.config;

    if (status !== 401) return Promise.reject(error);

    const url = originalRequest?.url || "";

    const isAuthCreate = url.includes("/auth/jwt/create/");
    const isAuthRefresh = url.includes("/auth/jwt/refresh/");

    if (isAuthCreate || isAuthRefresh) {
      clearTokens();
      window.location.href = "/login";
      return Promise.reject(error);
    }

    if (originalRequest?._retry) {
      clearTokens();
      window.location.href = "/login";
      return Promise.reject(error);
    }
    originalRequest._retry = true;

    try {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh((newToken) => {
            if (!newToken) return reject(error);
            originalRequest.headers = originalRequest.headers || {};
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            resolve(axiosClient(originalRequest));
          });
        });
      }

      isRefreshing = true;

      const newAccessToken = await refreshAccessToken();
      notifyTokenRefreshed(newAccessToken);

      originalRequest.headers = originalRequest.headers || {};
      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;

      return axiosClient(originalRequest);
    } catch (refreshErr) {
      clearTokens();
      window.location.href = "/login";
      return Promise.reject(refreshErr);
    } finally {
      isRefreshing = false;
    }
  }
);

export default axiosClient;
