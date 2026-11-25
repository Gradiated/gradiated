import { useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import type {
  ComponentPropsWithoutRef,
  ComponentType,
  ReactElement,
  ReactNode,
} from "react";

import { DocsAccount } from "../components/docs/DocsAccount";
import {
  DocsCodeBlock,
  DocsInlineCode,
} from "../components/docs/DocsCodeBlock";
import {
  DocsCodeTab,
  DocsCodeTabs,
  DocsCodeVariant,
  DocsCodeVariants,
} from "../components/docs/DocsCodeTabs";
import { DocsApiKeyAction } from "../components/docs/InteractiveQuickstart";
import { DocsModelCatalog } from "../components/docs/DocsModelCatalog";
import { DocsSessionProvider } from "../components/docs/DocsSession";
import DocsAnthropicSdk from "../docs/anthropic-sdk.mdx";
import DocsApiReference from "../docs/api-reference.mdx";
import DocsClaudeCode from "../docs/claude-code.mdx";
import DocsCodex from "../docs/codex.mdx";
import DocsErrors from "../docs/errors.mdx";
import DocsIndex from "../docs/index.mdx";
import DocsModelsPricing from "../docs/models-pricing.mdx";
import DocsOpenAiSdk from "../docs/openai-sdk.mdx";
import DocsOpenCode from "../docs/opencode.mdx";
import DocsQuickstart from "../docs/quickstart.mdx";
import DocsServiceTiers from "../docs/service-tiers.mdx";
import DocsSystemOneSdk from "../docs/systemone-sdk.mdx";
import DocsTrainingCustomLoops from "../docs/training/custom-loops.mdx";
import DocsTrainingEndpoints from "../docs/training/endpoints.mdx";
import DocsTrainingEnvironments from "../docs/training/environments.mdx";
import DocsTrainingOverview from "../docs/training/index.mdx";
import DocsTrainingRecipes from "../docs/training/recipes.mdx";
import DocsRecipeClassifier from "../docs/training/recipes/classifier.mdx";
import DocsRecipeDistillation from "../docs/training/recipes/distillation.mdx";
import DocsRecipeEmbeddings from "../docs/training/recipes/embeddings.mdx";
import DocsRecipeRewardModels from "../docs/training/recipes/reward-models.mdx";
import DocsRecipeRlAgents from "../docs/training/recipes/rl-agents.mdx";
import DocsRecipeRouter from "../docs/training/recipes/router.mdx";
import DocsRecipeSftDpo from "../docs/training/recipes/sft-dpo.mdx";
import DocsTrainingTrajectories from "../docs/training/trajectories.mdx";

type DocsDocument = {
  title: string;
  path: string;
  Component: ComponentType<Record<string, unknown>>;
};

export const documents = {
  index: {
    title: "Overview",
    path: "/docs/",
    Component: DocsIndex,
  },
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
  "systemone-sdk": {
    title: "SystemOne SDK",
    path: "/docs/systemone-sdk/",
    Component: DocsSystemOneSdk,
  },
  "service-tiers": {
    title: "Service tiers",
    path: "/docs/service-tiers/",
    Component: DocsServiceTiers,
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
  codex: {
    title: "Codex",
    path: "/docs/codex/",
    Component: DocsCodex,
  },
  "claude-code": {
    title: "Claude Code",
    path: "/docs/claude-code/",
    Component: DocsClaudeCode,
  },
  "training-overview": {
    title: "Overview",
    path: "/docs/training/",
    Component: DocsTrainingOverview,
  },
  "training-trajectories": {
    title: "Trajectories and data",
    path: "/docs/training/trajectories/",
    Component: DocsTrainingTrajectories,
  },
  "training-recipes": {
    title: "Recipes (Level 0 & 1)",
    path: "/docs/training/recipes/",
    Component: DocsTrainingRecipes,
  },
  "training-environments": {
    title: "Environments and rubrics",
    path: "/docs/training/environments/",
    Component: DocsTrainingEnvironments,
  },
  "training-custom-loops": {
    title: "Custom loops (Level 2)",
    path: "/docs/training/custom-loops/",
    Component: DocsTrainingCustomLoops,
  },
  "training-endpoints": {
    title: "Artifacts and endpoints",
    path: "/docs/training/endpoints/",
    Component: DocsTrainingEndpoints,
  },
  "recipe-router": {
    title: "Model router",
    path: "/docs/training/recipes/router/",
    Component: DocsRecipeRouter,
  },
  "recipe-classifier": {
    title: "Classifiers and decisions",
    path: "/docs/training/recipes/classifier/",
    Component: DocsRecipeClassifier,
  },
  "recipe-sft-dpo": {
    title: "Fine-tuning (SFT & DPO)",
    path: "/docs/training/recipes/sft-dpo/",
    Component: DocsRecipeSftDpo,
  },
  "recipe-rl-agents": {
    title: "RL for agents (GRPO)",
    path: "/docs/training/recipes/rl-agents/",
    Component: DocsRecipeRlAgents,
  },
  "recipe-distillation": {
    title: "Distillation and Cartridges",
    path: "/docs/training/recipes/distillation/",
    Component: DocsRecipeDistillation,
  },
  "recipe-reward-models": {
    title: "Reward models and verifiers",
    path: "/docs/training/recipes/reward-models/",
    Component: DocsRecipeRewardModels,
  },
  "recipe-embeddings": {
    title: "Embeddings and rerankers",
    path: "/docs/training/recipes/embeddings/",
    Component: DocsRecipeEmbeddings,
  },
  "api-reference": {
    title: "API reference",
    path: "/docs/api-reference/",
    Component: DocsApiReference,
  },
} satisfies Record<string, DocsDocument>;

export type DocsPageKey = keyof typeof documents;

export const navigation: Array<{ heading: string; items: DocsPageKey[] }> = [
  {
    heading: "Get started",
    items: ["index", "quickstart", "models-pricing"],
  },
  {
    heading: "Inference",
    items: [
      "openai-sdk",
      "anthropic-sdk",
      "systemone-sdk",
      "service-tiers",
      "errors",
    ],
  },
  {
    heading: "Training",
    items: [
      "training-overview",
      "training-trajectories",
      "training-recipes",
      "training-environments",
      "training-custom-loops",
      "training-endpoints",
    ],
  },
  {
    heading: "Recipe guides",
    items: [
      "recipe-router",
      "recipe-classifier",
      "recipe-sft-dpo",
      "recipe-rl-agents",
      "recipe-distillation",
      "recipe-reward-models",
      "recipe-embeddings",
    ],
  },
  { heading: "Integrations", items: ["opencode", "codex", "claude-code"] },
  { heading: "Reference", items: ["api-reference"] },
];

export const legacyPaths: Record<string, string> = {
  "/docs/api/": documents["api-reference"].path,
  "/docs/api-keys/": documents.quickstart.path,
  "/docs/billing/": documents.errors.path,
  "/docs/migrate/": documents.quickstart.path,
  "/docs/streaming/": documents["openai-sdk"].path,
  "/docs/tool-calling/": documents["openai-sdk"].path,
  "/docs/usage/": documents.index.path,
};

export const markdownPathFor = (path: string): string =>
  path === "/docs/" ? "/docs/index.md" : `${path.replace(/\/$/, "")}.md`;

const CopyIcon = (): ReactElement => (
  <svg
    aria-hidden="true"
    className="h-[18px] w-[18px]"
    fill="none"
    viewBox="0 0 20 20"
  >
    <rect height="12" rx="2" stroke="currentColor" width="12" x="6" y="6" />
    <path
      d="M4 14H3a2 2 0 0 1-2-2V3a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
      stroke="currentColor"
    />
  </svg>
);

const writeClipboardText = async (text: string): Promise<void> => {
  if (navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Use the browser fallback below.
    }
  }

  const input = document.createElement("textarea");
  input.value = text;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.append(input);
  input.select();
  const copied = document.execCommand("copy");
  input.remove();
  if (!copied) throw new Error("The browser could not copy the page.");
};

const DocsPageActions = ({
  markdownPath,
}: {
  markdownPath: string;
}): ReactElement => {
  const [copied, setCopied] = useState(false);

  const copyPage = async (): Promise<void> => {
    try {
      const response = await fetch(markdownPath);
      if (!response.ok) throw new Error("The Markdown page is not available.");
      const markdown = await response.text();
      await writeClipboardText(markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="relative z-10 float-right mb-5 ml-6 max-[600px]:float-none max-[600px]:mb-8 max-[600px]:ml-0">
      <button
        aria-label="Copy this page as Markdown"
        className="inline-flex cursor-pointer items-center gap-2.5 border border-ink bg-transparent px-4 py-2.5 font-site-mono text-[10px] font-medium uppercase tracking-[0.06em] text-ink transition-colors hover:bg-ink hover:text-paper"
        onClick={() => void copyPage()}
        type="button"
      >
        <CopyIcon />
        {copied ? "Copied" : "Copy page"}
      </button>
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
  <nav className="docs-section-nav section-nav" aria-label="Documentation">
    <h2>Docs</h2>
    {navigation.map((group) => (
      <div className="section-nav-group" key={group.heading}>
        <span>{group.heading}</span>
        {group.items.map((item) => (
          <Link
            aria-current={item === current ? "page" : undefined}
            key={item}
            to={documents[item].path}
          >
            {documents[item].title}
          </Link>
        ))}
      </div>
    ))}
  </nav>
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
      <aside className="max-[800px]:border-b max-[800px]:border-line max-[800px]:pb-7">
        <div className="max-[800px]:hidden">
          <DocsAccount />
        </div>
        <div className="mt-8 hidden min-[801px]:block">
          <DocsNavigation current={key} />
        </div>
        <details className="mt-7 min-[801px]:hidden max-[800px]:mt-0">
          <summary className="cursor-pointer text-[10px] uppercase tracking-label text-ink">
            Browse docs
          </summary>
          <div className="mt-6">
            <DocsNavigation current={key} />
          </div>
        </details>
      </aside>
      <article className="min-w-0">
        <DocsPageActions markdownPath={markdownPathFor(document.path)} />
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
      </article>
    </main>
  );
};

export const DocsPage = (): ReactElement => (
  <DocsSessionProvider>
    <DocsContent />
  </DocsSessionProvider>
);
