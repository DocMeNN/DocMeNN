import axiosClient from "./axiosClient";

export const getCart = () =>
  axiosClient.get("/pos/cart/");

export const addToCart = (payload) =>
  axiosClient.post("/pos/cart/items/", payload);
