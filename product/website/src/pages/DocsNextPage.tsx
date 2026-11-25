import { Children, isValidElement, useId, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import type { ComponentPropsWithoutRef, ReactElement, ReactNode } from "react";
import {
  Band,
  Footer,
  Module,
  Nav,
  SectionNavigation,
  SectionNavigationFab,
  Substrate,
} from "../components/design";
import type { SectionNavigationGroup } from "../components/design";
import { useRailDocNav } from "../components/design/RailShell";
import { DocsAccount } from "../components/docs/DocsAccount";
import { DocsApiKeyAction } from "../components/docs/InteractiveQuickstart";
import { DocsModelCatalog } from "../components/docs/DocsModelCatalog";
import { DocsSessionProvider } from "../components/docs/DocsSession";
import {
  documents,
  legacyPaths,
  markdownPathFor,
  navigation,
} from "./DocsPage";
import "../styles/index.css";

/**
 * The documentation, in the design system.
 *
 * Almost nothing here overrides an element. The MDX renders plain h1/p/ul/a/
 * code, and `.gr-doc` styles those directly — an override per element is how a
 * link ends up with no underline, because the day someone adds a new element
 * to a page nobody remembers to add a component for it. Two things do need a
 * wrapper: a code block, which carries a copy control, and a table, which has
 * to be able to scroll without the page scrolling with it.
 */

const getText = (node: ReactNode): string => {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(getText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) {
    return getText(node.props.children);
  }
  return "";
};

/** A sample and its copy control, as one object. */
const DocsPre = ({
  children,
  ...props
}: ComponentPropsWithoutRef<"pre">): ReactElement => {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    void navigator.clipboard
      .writeText(getText(children).trimEnd())
      .then(() => setCopied(true))
      .catch(() => setCopied(false));
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className="gr-doc-code">
      <button className="gr-doc-copy" onClick={copy} type="button">
        {copied ? "Copied" : "Copy"}
      </button>
      <pre {...props}>{children}</pre>
    </div>
  );
};

/* A table scrolls inside its own box. Letting the page scroll sideways for one
   wide table is how a docs page ends up with a horizontal scrollbar on every
   screen. */
const DocsTable = (props: ComponentPropsWithoutRef<"table">): ReactElement => (
  <div className="gr-doc-tablewrap">
    <table {...props} />
  </div>
);

const DocsLead = ({ children }: { children: ReactNode }): ReactElement => (
  <div className="gr-doc-lead">{children}</div>
);

const DocsNext = ({ children }: { children: ReactNode }): ReactElement => (
  <nav aria-label="Next" className="gr-doc-next">
    {children}
  </nav>
);

/* The tab controls are rewritten rather than reused: the shared ones carry
   their Tailwind look inline, including a dark shell built from the legacy
   `--code-bg`, and their "flatten the inner block" rules hook onto the old
   code component's data attribute. The logic is small; the styling is the
   whole point. */

type Labelled = { children: ReactNode; label: string };

export const DocsCodeTab = ({ children }: Labelled): ReactElement => (
  <>{children}</>
);

export const DocsCodeVariant = ({ children }: Labelled): ReactElement => (
  <>{children}</>
);

const useTabs = (children: ReactNode) => {
  const items = Children.toArray(children).filter(
    (child): child is ReactElement<Labelled> => isValidElement<Labelled>(child),
  );
  const [selected, setSelected] = useState(0);
  return { id: useId(), items, selected, setSelected };
};

/** Language tabs, ruled off above the sample they choose. */
export const DocsCodeTabs = ({
  action,
  children,
}: {
  action?: ReactNode;
  children: ReactNode;
}): ReactElement => {
  const { id, items, selected, setSelected } = useTabs(children);
  const active = items[selected] ?? items[0];

  return (
    <div className="gr-doc-tabs">
      <div className="gr-doc-tabs-head">
        <div
          aria-label="Code examples"
          className="gr-doc-tablist"
          role="tablist"
        >
          {items.map((tab, index) => (
            <button
              aria-controls={`${id}-panel-${index}`}
              aria-selected={selected === index}
              className="gr-doc-tab"
              id={`${id}-tab-${index}`}
              key={tab.props.label}
              onClick={() => setSelected(index)}
              role="tab"
              type="button"
            >
              {tab.props.label}
            </button>
          ))}
        </div>
        {action ? <div className="gr-doc-tabs-action">{action}</div> : null}
      </div>
      {active ? (
        <div
          aria-labelledby={`${id}-tab-${selected}`}
          id={`${id}-panel-${selected}`}
          role="tabpanel"
        >
          {active.props.children}
        </div>
      ) : null}
    </div>
  );
};

/** Request formats, chosen from a row INSIDE the sample's own surface. */
export const DocsCodeVariants = ({
  children,
}: {
  children: ReactNode;
}): ReactElement => {
  const { id, items, selected, setSelected } = useTabs(children);
  const active = items[selected] ?? items[0];

  return (
    <div className="gr-doc-variants">
      <div
        aria-label="Request format"
        className="gr-doc-variantlist"
        role="tablist"
      >
        {items.map((variant, index) => (
          <button
            aria-controls={`${id}-panel-${index}`}
            aria-selected={selected === index}
            className="gr-doc-tab"
            id={`${id}-tab-${index}`}
            key={variant.props.label}
            onClick={() => setSelected(index)}
            role="tab"
            type="button"
          >
            {variant.props.label}
          </button>
        ))}
      </div>
      {active ? (
        <div
          aria-labelledby={`${id}-tab-${selected}`}
          id={`${id}-panel-${selected}`}
          role="tabpanel"
        >
          {active.props.children}
        </div>
      ) : null}
    </div>
  );
};

const docsNavigation: SectionNavigationGroup[] = navigation.map((group) => ({
  heading: group.heading,
  items: group.items.map((item) => ({
    href: documents[item].path,
    label: documents[item].title,
  })),
}));

/** Copies the page as Markdown, or as a ready-to-paste coding agent prompt. */
const PageActions = ({
  path,
  title,
}: {
  path: string;
  title: string;
}): ReactElement => {
  const [copied, setCopied] = useState<"page" | "prompt" | null>(null);

  const copy = async (mode: "page" | "prompt") => {
    try {
      const mdPath = markdownPathFor(path);
      const response = await fetch(mdPath);
      if (!response.ok) throw new Error("No Markdown for this page.");
      const markdown = await response.text();

      const text =
        mode === "page"
          ? markdown
          : [
              `Use the Gradiated documentation for "${title}" to implement this in my repository.`,
              "",
              `Reference: https://gradiated.com${mdPath}`,
              "Full docs index: https://gradiated.com/llms.txt",
              "",
              "Guidelines:",
              "- Inspect my existing codebase first and match its language and conventions.",
              "- Read GRADIATED_API_KEY from the environment (or GRAD_BASE_URL for local mode); never hardcode secrets.",
              "- For training runs, run a dry run (`--dry-run --json` or `runs.plan()`) before launching GPU compute.",
              "",
              "Documentation:",
              "",
              markdown.trim(),
            ].join("\n");

      await navigator.clipboard.writeText(text);
      setCopied(mode);
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      setCopied(null);
    }
  };

  return (
    <div className="gr-doc-actions">
      <button
        aria-label="Copy this page as Markdown"
        className="gr-doc-copypage"
        onClick={() => void copy("page")}
        type="button"
      >
        {copied === "page" ? "Copied" : "Copy page"}
      </button>
      <button
        aria-label="Copy a coding agent prompt for this page"
        className="gr-doc-copypage"
        onClick={() => void copy("prompt")}
        type="button"
      >
        {copied === "prompt" ? "Copied" : "Copy prompt"}
      </button>
    </div>
  );
};

const DocsBody = (): ReactElement => {
  const location = useLocation();
  const path = location.pathname;

  /* The site rail carries the docs' contents — doc mode is a state of
     the ONE nav, so the page draws no sidebar of its own. */
  useRailDocNav({ title: "Docs", current: path, groups: docsNavigation });

  const redirect = legacyPaths[path];
  if (redirect) {
    return <Navigate replace to={redirect} />;
  }

  const entry = Object.entries(documents).find(
    ([, document]) => document.path === path,
  );
  if (!entry) return <Navigate replace to="/docs/" />;

  const [, document] = entry as [string, (typeof documents)["index"]];
  const Content = document.Component;

  return (
    <Substrate>
      <Nav />

      <Band>
        <Module className="gr-module--top" index={0}>
          <div className="gr-doc">
            {/* The sidebar's mobile form. Router links, like the sidebar's —
                an <a href> here reloads the document. Hidden above the wide
                tier, where the sticky sidebar does this job. */}
            <SectionNavigationFab
              current={document.path}
              groups={docsNavigation}
              label="Chapters"
            />

            <article className="gr-doc-main gr-prose">
              <PageActions path={document.path} title={document.title} />
              <Content
                components={{
                  pre: DocsPre,
                  table: DocsTable,
                  DocsApiKeyAction,
                  DocsCodeTab,
                  DocsCodeTabs,
                  DocsCodeVariant,
                  DocsCodeVariants,
                  DocsLead,
                  DocsModelCatalog,
                  DocsNext,
                }}
              />
            </article>
          </div>
        </Module>
      </Band>

      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};

export const DocsNextPage = (): ReactElement => (
  <DocsSessionProvider>
    <DocsBody />
  </DocsSessionProvider>
);
