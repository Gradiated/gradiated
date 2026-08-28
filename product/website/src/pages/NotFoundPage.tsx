import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import { SiteLink } from "../components/SiteLink";

export const NotFoundPage = (): ReactElement => (
  <main className="not-found">
    <p>404 / An unanswered question</p>
    <h1>What were you looking for?</h1>
    <span>The path ended here.</span>
    <nav>
      <Link to="/">
        Return home
        <ArrowRight aria-hidden="true" className="h-3 w-3" strokeWidth={1.5} />
      </Link>
      <Link to="/notes/our-thesis/">
        Read the thesis
        <ArrowRight aria-hidden="true" className="h-3 w-3" strokeWidth={1.5} />
      </Link>
      <SiteLink href="mailto:team@gradiated.com">
        Ask us directly
        <ArrowRight aria-hidden="true" className="h-3 w-3" strokeWidth={1.5} />
      </SiteLink>
    </nav>
  </main>
);
