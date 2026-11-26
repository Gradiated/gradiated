import {
  Children,
  createContext,
  isValidElement,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
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
  DocsCallout,
  DocsDeployFlow,
  DocsEnvLifecycle,
  DocsPipelineDiagram,
  DocsRecipeChooser,
  DocsTerminal,
  DocsTokenAlignment,
  DocsTrainingFlywheel,
} from "../components/docs/DocsTrainingInteractive";
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

const slugify = (value: string): string =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

const DocsHeading = ({
  as: Tag,
  children,
  ...props
}: ComponentPropsWithoutRef<"h2"> & { as: "h2" | "h3" }): ReactElement => {
  const id = props.id ?? slugify(getText(children));
  return (
    <Tag {...props} className={`gr-doc-heading ${props.className ?? ""}`} id={id || undefined}>
      {children}
      {id ? (
        <a aria-label={`Link to ${getText(children)}`} className="gr-doc-anchor" href={`#${id}`}>
          #
        </a>
      ) : null}
    </Tag>
  );
};

const DocsH2 = (props: ComponentPropsWithoutRef<"h2">): ReactElement => (
  <DocsHeading {...props} as="h2" />
);

const DocsH3 = (props: ComponentPropsWithoutRef<"h3">): ReactElement => (
  <DocsHeading {...props} as="h3" />
);

const SYNCED_LANGUAGES = new Set([
  "Python",
  "TypeScript",
  "JavaScript",
  "Go",
  "Rust",
  "CLI",
  "CLI (YAML)",
  "cURL",
]);

const DocsLanguageContext = createContext<{
  language: string | null;
  setLanguage: (lang: string) => void;
}>({ language: null, setLanguage: () => {} });

const DocsLanguageProvider = ({
  children,
}: {
  children: ReactNode;
}): ReactElement => {
  const [language, setLanguageState] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("gradiated.docs.lang");
      if (saved) setLanguageState(saved);
    } catch {
      // Ignore storage access errors.
    }
  }, []);

  const setLanguage = (lang: string) => {
    setLanguageState(lang);
    try {
      window.localStorage.setItem("gradiated.docs.lang", lang);
    } catch {
      // Ignore storage access errors.
    }
  };

  return (
    <DocsLanguageContext.Provider value={{ language, setLanguage }}>
      {children}
    </DocsLanguageContext.Provider>
  );
};

type Labelled = { children: ReactNode; label: string };

export const DocsCodeTab = ({ children }: Labelled): ReactElement => (
  <>{children}</>
);

export const DocsCodeVariant = ({ children }: Labelled): ReactElement => (
  <>{children}</>
);

const useTabs = (children: ReactNode, syncLanguage = false) => {
  const items = Children.toArray(children).filter(
    (child): child is ReactElement<Labelled> => isValidElement<Labelled>(child),
  );
  const { language, setLanguage } = useContext(DocsLanguageContext);
  const [localSelected, setLocalSelected] = useState(0);

  const isLanguageGroup =
    syncLanguage &&
    items.length > 0 &&
    items.some((item) => SYNCED_LANGUAGES.has(item.props.label));

  const syncedIndex =
    isLanguageGroup && language
      ? items.findIndex((item) => item.props.label === language)
      : -1;

  const selected = syncedIndex >= 0 ? syncedIndex : localSelected;

  const setSelected = (index: number) => {
    setLocalSelected(index);
    const chosen = items[index]?.props.label;
    if (isLanguageGroup && chosen && SYNCED_LANGUAGES.has(chosen)) {
      setLanguage(chosen);
    }
  };

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
  const { id, items, selected, setSelected } = useTabs(children, true);
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
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState<"page" | "prompt" | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const copy = async (mode: "page" | "prompt") => {
    setOpen(false);
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
              "- For training runs, run a dry run (`--dry-run --json` or `runs.plan()`) to check estimated tokens and cost before starting training.",
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
    <div className="gr-doc-actions" ref={containerRef}>
      <button
        aria-controls={menuId}
        aria-expanded={open}
        aria-haspopup="menu"
        className="gr-doc-copypage"
        onClick={() => setOpen((prev) => !prev)}
        type="button"
      >
        {copied ? (
          <svg
            aria-hidden="true"
            fill="none"
            height="13"
            stroke="currentColor"
            strokeLinecap="square"
            strokeLinejoin="miter"
            strokeWidth="1.6"
            viewBox="0 0 16 16"
            width="13"
          >
            <path d="M3 8.5 6.5 12 13 4.5" />
          </svg>
        ) : (
          <svg
            aria-hidden="true"
            fill="none"
            height="13"
            stroke="currentColor"
            strokeLinecap="square"
            strokeLinejoin="miter"
            strokeWidth="1.5"
            viewBox="0 0 16 16"
            width="13"
          >
            <rect height="9" width="9" x="5.5" y="5.5" />
            <path d="M10.5 5.5V2.5h-8v8h3" />
          </svg>
        )}
        <span>
          {copied === "page"
            ? "Copied page"
            : copied === "prompt"
              ? "Copied prompt"
              : "Copy"}
        </span>
        <svg
          aria-hidden="true"
          className="gr-doc-copypage-chevron"
          fill="none"
          height="11"
          stroke="currentColor"
          strokeLinecap="square"
          strokeLinejoin="miter"
          strokeWidth="1.6"
          viewBox="0 0 12 12"
          width="11"
        >
          <path d="M2.5 4.25 6 7.75l3.5-3.5" />
        </svg>
      </button>

      {open ? (
        <div className="gr-doc-copy-menu" id={menuId} role="menu">
          <button
            className="gr-doc-copy-item"
            onClick={() => void copy("page")}
            role="menuitem"
            type="button"
          >
            <span className="gr-doc-copy-item-title">Copy page</span>
            <span className="gr-doc-copy-item-desc">
              Raw Markdown (.md)
            </span>
          </button>
          <button
            className="gr-doc-copy-item"
            onClick={() => void copy("prompt")}
            role="menuitem"
            type="button"
          >
            <span className="gr-doc-copy-item-title">Copy prompt</span>
            <span className="gr-doc-copy-item-desc">
              Ready-to-paste coding agent prompt
            </span>
          </button>
        </div>
      ) : null}
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
                  h2: DocsH2,
                  h3: DocsH3,
                  pre: DocsPre,
                  table: DocsTable,
                  DocsApiKeyAction,
                  DocsCallout,
                  DocsCodeTab,
                  DocsCodeTabs,
                  DocsCodeVariant,
                  DocsCodeVariants,
                  DocsDeployFlow,
                  DocsEnvLifecycle,
                  DocsLead,
                  DocsModelCatalog,
                  DocsNext,
                  DocsPipelineDiagram,
                  DocsRecipeChooser,
                  DocsTerminal,
                  DocsTokenAlignment,
                  DocsTrainingFlywheel,
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
    <DocsLanguageProvider>
      <DocsBody />
    </DocsLanguageProvider>
  </DocsSessionProvider>
);
