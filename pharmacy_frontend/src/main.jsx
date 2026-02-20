/**
 * ======================================================
 * PATH: src/main.jsx
 * ======================================================
 *
 * APP ENTRYPOINT
 * - Mount React root
 * - BrowserRouter wraps the entire app
 * - StrictMode enabled (dev-only warnings + best practices)
 * ======================================================
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
