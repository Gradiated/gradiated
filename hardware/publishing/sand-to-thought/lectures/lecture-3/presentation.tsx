import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { FabricationJourney } from "../../articles/fabricating-a-transistor/figures/FabricationJourney";
import "../../../../../product/website/src/legacy.css";
import "../../../../../product/website/src/tailwind.css";
import "../../../../../product/website/src/styles/index.css";
import "./presentation.css";

const root = document.getElementById("root");
if (!root) throw new Error("The lecture root element is missing.");

createRoot(root).render(
  <StrictMode>
    <div className="gr-root">
      <FabricationJourney lecture />
    </div>
  </StrictMode>,
);
