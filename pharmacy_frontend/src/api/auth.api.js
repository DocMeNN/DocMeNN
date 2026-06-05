import axiosClient from "./axiosClient";

export const login = (credentials) =>
  axiosClient.post("/auth/login/", credentials);

export const getMe = () =>
  axiosClient.get("/auth/me/");
