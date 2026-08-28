import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import { ThesisContent } from "../content";

export const ArticlePage = (): ReactElement => (
  <main className="article">
    <Link className="eyebrow" to="/library/">
      ← Library
    </Link>
    <p className="article-date">2026-07-13</p>
    <h1>Thesis</h1>
    <ThesisContent />
  </main>
);
