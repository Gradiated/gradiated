import { Link } from "react-router-dom";
import type { ComponentType, ReactElement } from "react";
import DocsIndex from "../docs/index.mdx";
import DocsApi from "../docs/api.mdx";
import DocsCodex from "../docs/codex.mdx";
import DocsOpenCode from "../docs/opencode.mdx";
import DocsQuickstart from "../docs/quickstart.mdx";

export type DocsPageKey = "index" | "quickstart" | "opencode" | "codex" | "api";

type DocsPageProps = {
  page: DocsPageKey;
};

type DocsDocument = {
  title: string;
  path: string;
  label: string;
  Component: ComponentType<Record<string, unknown>>;
};

const documents: Record<DocsPageKey, DocsDocument> = {
  index: {
    title: "Use Gradiated inference",
    path: "/docs/",
    label: "Overview",
    Component: DocsIndex,
  },
  quickstart: {
    title: "Quickstart",
    path: "/docs/quickstart/",
    label: "Get started",
    Component: DocsQuickstart,
  },
  opencode: {
    title: "OpenCode",
    path: "/docs/opencode/",
    label: "Coding agents",
    Component: DocsOpenCode,
  },
  codex: {
    title: "Codex",
    path: "/docs/codex/",
    label: "Coding agents",
    Component: DocsCodex,
  },
  api: {
    title: "Chat Completions API",
    path: "/docs/api/",
    label: "API",
    Component: DocsApi,
  },
};

const navigation: Array<{ heading: string; items: DocsPageKey[] }> = [
  { heading: "Get started", items: ["index", "quickstart"] },
  { heading: "Coding agents", items: ["opencode", "codex"] },
  { heading: "API", items: ["api"] },
];

export const DocsPage = ({ page }: DocsPageProps): ReactElement => {
  const document = documents[page];
  const Content = document.Component;

  return (
    <main className="docs-page">
      <aside className="docs-sidebar" aria-label="Documentation">
        <Link className="docs-back" to="/">
          ← Gradiated
        </Link>
        {navigation.map((group) => (
          <div className="docs-nav-group" key={group.heading}>
            <p>{group.heading}</p>
            <nav>
              {group.items.map((item) => (
                <Link
                  className={item === page ? "active" : ""}
                  key={item}
                  to={documents[item].path}
                >
                  {documents[item].title}
                </Link>
              ))}
            </nav>
          </div>
        ))}
      </aside>
      <article className="docs-article">
        <div className="docs-article-topline">
          <span>{document.label}</span>
          <span>Gradiated Docs</span>
        </div>
        <Content />
      </article>
    </main>
  );
};
