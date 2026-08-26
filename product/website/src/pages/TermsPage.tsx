import { TermsContent } from "../content";
import type { ReactElement } from "react";

export const TermsPage = (): ReactElement => (
  <main className="article legal">
    <p className="eyebrow">Terms of Service</p>
    <h1>Terms</h1>
    <TermsContent />
  </main>
);
