// src/context/AuthContext.jsx

import { createContext, useContext, useEffect, useState } from "react";
import axiosClient from "../api/axiosClient";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // 🔄 Restore auth state on app load
  useEffect(() => {
    try {
      const storedUser = localStorage.getItem("user");
      const accessToken = localStorage.getItem("access_token");

      if (storedUser && accessToken) {
        setUser(JSON.parse(storedUser));
      }
    } catch (err) {
      console.error("Failed to restore auth state:", err);
      localStorage.clear();
    } finally {
      setLoading(false);
    }
  }, []);

  // 🔐 LOGIN (NO AUTH HEADER — CRITICAL)
  const login = async (email, password) => {
    try {
      const response = await axiosClient.post(
        "/auth/login/",
        { email, password },
        {
          // 🔥 explicitly ensure no credentials leakage
          headers: {
            Authorization: undefined,
          },
        }
      );

      const { access, refresh, user } = response.data || {};

      if (!access || !refresh || !user) {
        throw new Error("Invalid login response from server");
      }

      localStorage.setItem("access_token", access);
      localStorage.setItem("refresh_token", refresh);
      localStorage.setItem("user", JSON.stringify(user));

      setUser(user);
      return user;
    } catch (error) {
      console.error(
        "Login failed:",
        error?.response?.data || error.message
      );
      throw error;
    }
  };

  // 🚪 LOGOUT
  const logout = () => {
    localStorage.clear();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: Boolean(user),
        loading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
