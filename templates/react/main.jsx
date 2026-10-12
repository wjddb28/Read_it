import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "../../static/css/react/home.css";
import "../../static/css/react/auth.css";
import "../../static/css/react/features.css";
import "../../static/css/react/refresh.css";
createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
