import { DpaContent } from "../content";
import type { ReactElement } from "react";

export const DpaPage = (): ReactElement => (
  <main className="article legal">
    <p className="eyebrow">Data Processing Addendum</p>
    <h1>DPA</h1>
    <DpaContent />
  </main>
);
