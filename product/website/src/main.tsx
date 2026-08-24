import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./legacy.css";
import "./tailwind.css";

const root = document.getElementById("root");

if (!root) throw new Error("The React root element is missing.");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
