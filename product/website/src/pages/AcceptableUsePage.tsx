import { AcceptableUseContent } from "../content";
import type { ReactElement } from "react";

export const AcceptableUsePage = (): ReactElement => (
  <main className="article legal">
    <p className="eyebrow">Acceptable Use Policy</p>
    <h1>Acceptable use</h1>
    <AcceptableUseContent />
  </main>
);
