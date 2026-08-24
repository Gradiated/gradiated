import { PrivacyContent } from "../content";
import type { ReactElement } from "react";

export const PrivacyPage = (): ReactElement => (
  <main className="article legal">
    <p className="eyebrow">Privacy Policy</p>
    <h1>Privacy</h1>
    <PrivacyContent />
  </main>
);
