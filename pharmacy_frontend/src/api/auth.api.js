// src/api/auth.api.js

import axiosClient from "./axiosClient";

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

  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);

  // /auth/me/ requires Authorization header; interceptor attaches it
  const meRes = await axiosClient.get("/auth/me/");
  return meRes.data;
};

export const getMe = async () => {
  return axiosClient.get("/auth/me/");
};

export const logout = () => {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
};
