/**
 * ======================================================
 * PATH: src/api/auth.api.js
 * ======================================================
 *
 * AUTH API
 * - POST /auth/jwt/create/  -> { access, refresh }
 * - GET  /auth/me/          -> user profile (requires Authorization)
 *
 * Tokens are persisted via lib/auth.js (single standard keys)
 * ======================================================
 */

import axiosClient from "./axiosClient";
import { saveTokens, clearTokens } from "../lib/auth";

/**
 * Login user
 * - Gets JWT tokens
 * - Fetches user profile
 * - Returns user
 */
export const login = async ({ email, password }) => {
  const tokenRes = await axiosClient.post("/auth/jwt/create/", {
    email,
    password,
  });

  const { access, refresh } = tokenRes.data || {};

  if (!access || !refresh) {
    throw new Error("Token creation failed");
  }

  // Single standard keys used everywhere
  saveTokens(access, refresh);

  // /auth/me/ requires Authorization header; axiosClient interceptor should attach it
  const meRes = await axiosClient.get("/auth/me/");
  return meRes.data;
};

export const getMe = async () => {
  return axiosClient.get("/auth/me/");
};

export const logout = () => {
  clearTokens();
};
