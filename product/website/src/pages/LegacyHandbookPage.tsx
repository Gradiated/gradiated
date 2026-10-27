import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import {
  handbookPages,
  handbookSections,
  type HandbookSlug,
} from "../handbook";

type LegacyHandbookPageProps = {
  slug: HandbookSlug;
};

export const LegacyHandbookPage = ({
  slug,
}: LegacyHandbookPageProps): ReactElement => {
  const page = handbookPages.find((candidate) => candidate.slug === slug)!;
  const Content = page.Content;

  return (
    <main className="article handbook-article handbook-page">
      <nav className="handbook-nav section-nav" aria-label="Handbook">
        <h2>Handbook</h2>
        {handbookSections.map((section) => (
          <div className="section-nav-group" key={section.label}>
            <span>{section.label}</span>
            {section.pages.map((item) => (
              <Link
                aria-current={item.slug === slug ? "page" : undefined}
                key={item.slug}
                to={`/handbook/${item.slug}/`}
              >
                {item.title}
              </Link>
            ))}
          </div>
        ))}
      </nav>
      <div className="handbook-content">
        <Link className="eyebrow inline-flex items-center gap-2" to="/handbook/">
          <ArrowLeft aria-hidden="true" className="h-3 w-3" strokeWidth={1.5} />
          Handbook
        </Link>
        <h1>{page.title}</h1>
        <Content />
      </div>
    </main>
  );
};
