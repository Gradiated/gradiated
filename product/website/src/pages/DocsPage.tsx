import { isValidElement, lazy, Suspense, useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import type {
  ComponentPropsWithoutRef,
  ComponentType,
  ReactElement,
  ReactNode,
} from "react";

import { DocsAccount } from "../components/docs/DocsAccount";
import {
  DocsCodeTab,
  DocsCodeTabs,
  DocsCodeVariant,
  DocsCodeVariants,
} from "../components/docs/DocsCodeTabs";
import { DocsApiKeyAction } from "../components/docs/InteractiveQuickstart";
import { DocsModelCatalog } from "../components/docs/DocsModelCatalog";
import { DocsSessionProvider } from "../components/docs/DocsSession";

const DocsIndex = lazy(() => import("../docs/index.mdx"));
const DocsQuickstart = lazy(() => import("../docs/quickstart.mdx"));
const DocsModelsPricing = lazy(() => import("../docs/models-pricing.mdx"));
const DocsOpenAiSdk = lazy(() => import("../docs/openai-sdk.mdx"));
const DocsAnthropicSdk = lazy(() => import("../docs/anthropic-sdk.mdx"));
const DocsServiceTiers = lazy(() => import("../docs/service-tiers.mdx"));
const DocsStreaming = lazy(() => import("../docs/streaming.mdx"));
const DocsToolCalling = lazy(() => import("../docs/tool-calling.mdx"));
const DocsParameters = lazy(() => import("../docs/parameters.mdx"));
const DocsErrors = lazy(() => import("../docs/errors.mdx"));
const DocsOpenCode = lazy(() => import("../docs/opencode.mdx"));
const DocsCodex = lazy(() => import("../docs/codex.mdx"));
const DocsClaudeCode = lazy(() => import("../docs/claude-code.mdx"));
const DocsApiReference = lazy(() => import("../docs/api-reference.mdx"));

type DocsDocument = {
  title: string;
  path: string;
  Component: ComponentType<Record<string, unknown>>;
};

const documents = {
  index: { title: "Overview", path: "/docs/", Component: DocsIndex },
  quickstart: {
    title: "Quickstart",
    path: "/docs/quickstart/",
    Component: DocsQuickstart,
  },
  "models-pricing": {
    title: "Models and pricing",
    path: "/docs/models-pricing/",
    Component: DocsModelsPricing,
  },
  "openai-sdk": {
    title: "OpenAI SDK",
    path: "/docs/openai-sdk/",
    Component: DocsOpenAiSdk,
  },
  "anthropic-sdk": {
    title: "Anthropic SDK",
    path: "/docs/anthropic-sdk/",
    Component: DocsAnthropicSdk,
  },
  "service-tiers": {
    title: "Service tiers",
    path: "/docs/service-tiers/",
    Component: DocsServiceTiers,
  },
  streaming: {
    title: "Streaming",
    path: "/docs/streaming/",
    Component: DocsStreaming,
  },
  "tool-calling": {
    title: "Tool calling",
    path: "/docs/tool-calling/",
    Component: DocsToolCalling,
  },
  parameters: {
    title: "Parameters and model support",
    path: "/docs/parameters/",
    Component: DocsParameters,
  },
  errors: {
    title: "Errors, limits, and retries",
    path: "/docs/errors/",
    Component: DocsErrors,
  },
  opencode: {
    title: "OpenCode",
    path: "/docs/opencode/",
    Component: DocsOpenCode,
  },
  codex: { title: "Codex", path: "/docs/codex/", Component: DocsCodex },
  "claude-code": {
    title: "Claude Code",
    path: "/docs/claude-code/",
    Component: DocsClaudeCode,
  },
  "api-reference": {
    title: "API reference",
    path: "/docs/api-reference/",
    Component: DocsApiReference,
  },
} satisfies Record<string, DocsDocument>;

type DocsPageKey = keyof typeof documents;

const navigation: Array<{ heading: string; items: DocsPageKey[] }> = [
  {
    heading: "Get started",
    items: ["index", "quickstart", "models-pricing"],
  },
  {
    heading: "Inference",
    items: [
      "openai-sdk",
      "anthropic-sdk",
      "service-tiers",
      "streaming",
      "tool-calling",
      "parameters",
      "errors",
    ],
  },
  { heading: "Integrations", items: ["opencode", "codex", "claude-code"] },
  { heading: "Reference", items: ["api-reference"] },
];

const legacyPaths: Record<string, string> = {
  "/docs/api/": documents["api-reference"].path,
  "/docs/api-keys/": documents.quickstart.path,
  "/docs/billing/": documents.errors.path,
  "/docs/migrate/": documents.quickstart.path,
  "/docs/usage/": documents.index.path,
};

const getCodeText = (node: ReactNode): string => {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) return node.map(getCodeText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) {
    return getCodeText(node.props.children);
  }
  return "";
};

const DocsCodeBlock = ({
  children,
  className = "",
  ...props
}: ComponentPropsWithoutRef<"pre">): ReactElement => {
  const [copied, setCopied] = useState(false);
  const copyCode = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(getCodeText(children).trimEnd());
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div
      className="relative my-[27px] [&_.hljs-attr]:text-[var(--code-string)] [&_.hljs-attribute]:text-[var(--code-fg)] [&_.hljs-built_in]:text-[var(--code-accent)] [&_.hljs-comment]:text-[var(--code-muted)] [&_.hljs-keyword]:text-[var(--code-accent)] [&_.hljs-literal]:text-[var(--code-string)] [&_.hljs-meta]:text-[var(--code-muted)] [&_.hljs-number]:text-[var(--code-string)] [&_.hljs-params]:text-[var(--code-muted)] [&_.hljs-property]:text-[var(--code-fg)] [&_.hljs-string]:text-[var(--code-string)] [&_.hljs-title.class_]:text-[var(--code-accent)] [&_.hljs-title.function_]:text-[var(--code-fg)] [&_.hljs-type]:text-[var(--code-accent)] [&_.hljs-variable]:text-[var(--code-muted)]"
      data-docs-code-block
    >
      <button
        className="absolute right-4 top-3 z-[1] cursor-pointer border-0 bg-transparent px-2 py-1 font-site-mono text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--code-muted)] hover:text-[var(--code-fg)] focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-[var(--code-fg)]"
        onClick={copyCode}
        type="button"
      >
        {copied ? "Copied" : "Copy"}
      </button>
      <pre
        className={`m-0 overflow-x-auto rounded-xl border border-[var(--code-border)] bg-[var(--code-bg)] px-6 py-[22px] pr-24 font-site-mono text-[12.5px] leading-[1.72] text-[var(--code-fg)] shadow-[var(--code-shadow)] max-[500px]:px-4 max-[500px]:py-[18px] max-[500px]:text-[11.5px] ${className}`}
        {...props}
      >
        {children}
      </pre>
    </div>
  );
};

const DocsH1 = (props: ComponentPropsWithoutRef<"h1">): ReactElement => (
  <h1
    {...props}
    className={`mb-[18px] mt-0 max-w-[760px] font-newsreader text-[clamp(38px,4.5vw,54px)] font-medium leading-none tracking-[-0.052em] max-[500px]:text-[40px] ${props.className ?? ""}`}
  />
);

const DocsH2 = (props: ComponentPropsWithoutRef<"h2">): ReactElement => (
  <h2
    {...props}
    className={`mb-[14px] mt-[58px] font-newsreader text-[32px] font-medium leading-none tracking-[-0.042em] max-[500px]:mt-12 max-[500px]:text-[29px] ${props.className ?? ""}`}
  />
);

const DocsH3 = (props: ComponentPropsWithoutRef<"h3">): ReactElement => (
  <h3
    {...props}
    className={`mb-[9px] mt-8 font-libre text-[17px] font-semibold leading-[1.3] ${props.className ?? ""}`}
  />
);

const DocsParagraph = (props: ComponentPropsWithoutRef<"p">): ReactElement => (
  <p
    {...props}
    className={`mb-[17px] mt-0 max-w-[680px] font-libre text-[16px] leading-[1.68] max-[500px]:text-[15px] ${props.className ?? ""}`}
  />
);

const listClass =
  "mb-6 mt-0 max-w-[680px] pl-[22px] font-libre text-[16px] leading-[1.68] max-[500px]:text-[15px]";

const DocsUnorderedList = (
  props: ComponentPropsWithoutRef<"ul">,
): ReactElement => (
  <ul {...props} className={`${listClass} ${props.className ?? ""}`} />
);

const DocsOrderedList = (
  props: ComponentPropsWithoutRef<"ol">,
): ReactElement => (
  <ol {...props} className={`${listClass} ${props.className ?? ""}`} />
);

const DocsListItem = (props: ComponentPropsWithoutRef<"li">): ReactElement => (
  <li {...props} className={`my-1 pl-1 ${props.className ?? ""}`} />
);

const DocsAnchor = (props: ComponentPropsWithoutRef<"a">): ReactElement => (
  <a
    {...props}
    className={`text-accent underline decoration-line underline-offset-[3px] ${props.className ?? ""}`}
  />
);

const DocsInlineCode = (
  props: ComponentPropsWithoutRef<"code">,
): ReactElement => {
  const block = props.className?.includes("hljs");
  return (
    <code
      {...props}
      className={
        block
          ? `bg-transparent p-0 font-inherit ${props.className ?? ""}`
          : `bg-[rgba(28,27,24,0.08)] px-[5px] py-0.5 font-site-mono text-[0.88em] font-medium leading-[1.4] ${props.className ?? ""}`
      }
    />
  );
};

const DocsTable = (props: ComponentPropsWithoutRef<"table">): ReactElement => (
  <div className="my-7 max-w-[760px] overflow-x-auto">
    <table
      {...props}
      className={`w-full border-collapse font-libre text-[13px] leading-normal ${props.className ?? ""}`}
    />
  </div>
);

const DocsTableHead = (props: ComponentPropsWithoutRef<"th">): ReactElement => (
  <th
    {...props}
    className={`border-b border-line py-3 pr-3 text-left align-top font-site-mono text-[10px] font-medium uppercase tracking-[0.06em] text-muted ${props.className ?? ""}`}
  />
);

const DocsTableCell = (props: ComponentPropsWithoutRef<"td">): ReactElement => (
  <td
    {...props}
    className={`border-b border-line py-3 pr-3 text-left align-top ${props.className ?? ""}`}
  />
);

const DocsDiv = (props: ComponentPropsWithoutRef<"div">): ReactElement => (
  <div {...props} />
);

const DocsLead = ({ children }: { children: ReactNode }): ReactElement => (
  <div className="mb-[34px] max-w-[660px] font-libre text-[17px] leading-relaxed text-muted">
    {children}
  </div>
);

const DocsNext = ({ children }: { children: ReactNode }): ReactElement => (
  <div className="mt-16 grid grid-cols-2 gap-[18px] max-[500px]:grid-cols-1 [&_a]:block [&_a]:border-t [&_a]:border-ink [&_a]:py-[18px] [&_a]:text-ink [&_a]:no-underline [&_small]:mb-[13px] [&_small]:block [&_small]:font-site-mono [&_small]:text-[10px] [&_small]:font-medium [&_small]:uppercase [&_small]:tracking-[0.06em] [&_small]:text-muted [&_strong]:block [&_strong]:font-newsreader [&_strong]:text-[23px] [&_strong]:font-medium [&_strong]:leading-tight [&_strong]:tracking-[-0.035em]">
    {children}
  </div>
);

const DocsNavigation = ({
  current,
}: {
  current: DocsPageKey;
}): ReactElement => (
  <>
    {navigation.map((group) => (
      <div className="mb-7" key={group.heading}>
        <p className="mb-2.5 mt-0 text-[10px] uppercase tracking-[0.08em] text-muted">
          {group.heading}
        </p>
        <nav className="grid gap-2">
          {group.items.map((item) => (
            <Link
              className={`relative text-[11px] transition-colors hover:text-ink ${
                item === current
                  ? "text-ink before:absolute before:-left-[13px] before:top-[0.42em] before:h-[5px] before:w-[5px] before:rounded-full before:bg-accent"
                  : "text-muted"
              }`}
              key={item}
              to={documents[item].path}
            >
              {documents[item].title}
            </Link>
          ))}
        </nav>
      </div>
    ))}
  </>
);

const DocsContent = (): ReactElement => {
  const location = useLocation();
  const redirect = legacyPaths[location.pathname];
  if (redirect) return <Navigate replace to={redirect} />;

  const entry = Object.entries(documents).find(
    ([, document]) => document.path === location.pathname,
  );
  if (!entry) {
    return (
      <main className="mx-auto min-h-[60vh] max-w-content px-7 py-20">
        <h1 className="font-newsreader text-5xl tracking-heading">
          Page not found
        </h1>
        <Link className="mt-6 inline-block text-accent underline" to="/docs/">
          Open the docs overview
        </Link>
      </main>
    );
  }

  const [key, document] = entry as [DocsPageKey, DocsDocument];
  const Content = document.Component;

  return (
    <main className="mx-auto grid min-h-[calc(100vh-154px)] max-w-[1180px] grid-cols-[220px_minmax(0,760px)] gap-[76px] px-6 pb-[120px] pt-16 max-[800px]:grid-cols-1 max-[800px]:gap-10 max-[800px]:px-[22px] max-[800px]:pb-[90px] max-[800px]:pt-12">
      <aside
        className="font-site-mono text-[11px] leading-[1.35] max-[800px]:border-b max-[800px]:border-line max-[800px]:pb-7"
        aria-label="Documentation"
      >
        <Link
          className="mb-8 inline-block border-b border-ink pb-1 text-ink"
          to="/"
        >
          ← Gradiated
        </Link>
        <DocsAccount />
        <div className="mt-8 hidden min-[801px]:block">
          <DocsNavigation current={key} />
        </div>
        <details className="mt-7 min-[801px]:hidden">
          <summary className="cursor-pointer text-[10px] uppercase tracking-label text-ink">
            Browse docs
          </summary>
          <div className="mt-6 grid grid-cols-2 gap-x-8 max-[500px]:grid-cols-1">
            <DocsNavigation current={key} />
          </div>
        </details>
      </aside>
      <article className="min-w-0">
        <Suspense
          fallback={
            <p className="font-libre text-sm text-muted">Loading page…</p>
          }
        >
          <Content
            components={{
              a: DocsAnchor,
              code: DocsInlineCode,
              div: DocsDiv,
              h1: DocsH1,
              h2: DocsH2,
              h3: DocsH3,
              li: DocsListItem,
              ol: DocsOrderedList,
              p: DocsParagraph,
              pre: DocsCodeBlock,
              table: DocsTable,
              td: DocsTableCell,
              th: DocsTableHead,
              ul: DocsUnorderedList,
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
        </Suspense>
      </article>
    </main>
  );
};

export const DocsPage = (): ReactElement => (
  <DocsSessionProvider>
    <DocsContent />
  </DocsSessionProvider>
);
