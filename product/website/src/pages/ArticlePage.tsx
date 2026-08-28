import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import { ThesisContent } from "../content";

export const ArticlePage = (): ReactElement => (
  <main className="article">
    <Link className="eyebrow inline-flex items-center gap-2" to="/library/">
      <ArrowLeft aria-hidden="true" className="h-3 w-3" strokeWidth={1.5} />
      Library
    </Link>
    <p className="article-date">2026-07-13</p>
    <h1>Thesis</h1>
    <ThesisContent />
  </main>
);
