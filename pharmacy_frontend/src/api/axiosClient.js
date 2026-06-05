// src/api/axiosClient.js

import axios from "axios";

const axiosClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",

  headers: {
    "Content-Type": "application/json",
  },
});

/**
 * 🔐 Request interceptor
 * Attach Authorization header ONLY when token exists
 * AND request is NOT login or register
 */
axiosClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("access_token");

    const isAuthEndpoint =
      config.url?.includes("/auth/login/") ||
      config.url?.includes("/auth/register/");

    if (token && !isAuthEndpoint) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

/**
 * 🚨 Global 401 handler
 */
axiosClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.clear();
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default axiosClient;
