import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import { methodPages, methodSections, type MethodSlug } from "../method";

type MethodPageProps = {
  slug: MethodSlug;
};

export const MethodPage = ({ slug }: MethodPageProps): ReactElement => {
  const page = methodPages.find((candidate) => candidate.slug === slug)!;
  const Content = page.Content;

  return (
    <main className="article handbook-article method-page">
      <nav className="method-nav section-nav" aria-label="Method">
        <h2>Method</h2>
        {methodSections.map((section) => (
          <div className="section-nav-group" key={section.label}>
            <span>{section.label}</span>
            {section.pages.map((item) => (
              <Link
                aria-current={item.slug === slug ? "page" : undefined}
                key={item.slug}
                to={`/methods/${item.slug}/`}
              >
                {item.title}
              </Link>
            ))}
          </div>
        ))}
      </nav>
      <div className="method-content">
        <Link className="eyebrow inline-flex items-center gap-2" to="/methods/">
          <ArrowLeft aria-hidden="true" className="h-3 w-3" strokeWidth={1.5} />
          Library
        </Link>
        <h1>{page.title}</h1>
        <Content />
      </div>
    </main>
  );
};
