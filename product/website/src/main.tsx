import { StrictMode } from "react";
import { createRoot, hydrateRoot } from "react-dom/client";
import { App } from "./App";
import "./analytics";
import "./legacy.css";
import "./tailwind.css";

const root = document.getElementById("root");

if (!root) throw new Error("The React root element is missing.");

const app = (
  <StrictMode>
    <App />
  </StrictMode>
);

if (root.hasChildNodes()) hydrateRoot(root, app);
else createRoot(root).render(app);
