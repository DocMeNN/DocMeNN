// src/lib/auth.js

// Where we store JWT tokens
const ACCESS_KEY = "accessToken";
const REFRESH_KEY = "refreshToken";

// Save tokens to localStorage
export function saveTokens(access, refresh) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
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

// Decode JWT to get payload (role, email, id)
export function decodeJWT(token) {
  try {
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload));
  } catch (e) {
    return null;
  }
}

// Get user information from token
export function getUserFromToken() {
  const access = getAccessToken();
  if (!access) return null;

  return decodeJWT(access);
}

// Check if user is authenticated
export function isLoggedIn() {
  return !!getAccessToken();
}

// Check if user has a role (Admin, Cashier, Pharmacist, Reception)
export function hasRole(role) {
  const user = getUserFromToken();
  return user?.role === role;
}
