/**
 * The models with pages — what each one is, what it is good for, and the
 * numbers a developer checks before committing to one.
 *
 * The goal of a model page (per the product thread): interesting to a
 * developer, but the page exists so they finish it thinking "let's
 * post-train this". Every page ends at that door.
 *
 * PRICING AND CONTEXT are written here as static mirrors of the control
 * catalog (packages/control/src/catalog/models/*), which is also what the
 * API serves — same numbers, same source. ModelVitals on the page refreshes
 * them from the live API after mount, so a repriced model corrects itself
 * without a website deploy.
 *
 * BENCHMARKS are published figures, not ours: the maker's reported scores
 * and independent evals, as of early October 2026. Each set carries its own
 * note saying whose numbers they are. Do not add a score here without a
 * source — an invented benchmark on a marketing page is the expensive kind
 * of bug.
 */

export type ModelBenchmark = {
  name: string;
  score: string;
  /** 0–100, drives the bar. Omit where the scale would mislead. */
  bar?: number;
  note?: string;
};

export type ModelSnippet = {
  label: string;
  code: string;
};

export type ModelPageData = {
  /** URL slug under /models/. */
  slug: string;
  /** The API model id — what `model:` is set to, and the join key for live vitals. */
  id: string;
  name: string;
  maker: string;
  /** The two-or-three letter stand-in until each model has its mark. */
  mark: string;
  /** Provider mark from /assets/models/, where one exists. Kev has none —
   *  its monogram stands in. */
  icon?: string;
  oneLiner: string;
  tags: string[];
  overview: string[];
  goodFor: { title: string; body: string }[];
  benchmarks: ModelBenchmark[];
  benchmarksNote: string;
  specs: { label: string; value: string }[];
  /** Static mirror of the catalog; ModelVitals refreshes it live. */
  vitals: {
    input: string;
    cachedInput: string;
    output: string;
    context: string;
  };
  gettingStarted: {
    lede: string;
    snippets: ModelSnippet[];
    docsHref: string;
    docsLabel: string;
  };
};

export const models: ModelPageData[] = [
  {
    slug: "deepseek-v4-1-flash",
    id: "deepseek/deepseek-v4.1-flash",
    name: "DeepSeek V4.1 Flash",
    maker: "DeepSeek",
    mark: "DS",
    icon: "/assets/models/deepseek-color.svg",
    oneLiner:
      "A frontier-class generalist at flash-tier prices: a million tokens of context, strong agentic coding, and output fast enough to sit in an interactive loop.",
    tags: ["Open weights", "1M context", "FP4 on Gradiated", "Tool use"],
    overview: [
      "DeepSeek V4.1 Flash is the efficiency cut of the V4 family: the same million-token context as its larger siblings, with aggressive KV-cache compression and speculative decoding doing the work of keeping it fast and cheap. We serve it with TP4 and DSpark speculative decoding.",
      "It benchmarks like a frontier model on knowledge and reasoning, and holds the top of its class on agentic coding — which makes it the default choice when you want one model to cover chat, code, and long-document work before specialising it on your own traffic.",
    ],
    goodFor: [
      {
        title: "Agentic coding.",
        body: "Top of its cohort on DeepSWE and terminal-driven work. A capable base for coding agents before post-training sharpens it on your repository.",
      },
      {
        title: "Long-context work.",
        body: "A million tokens of context at a price that lets you actually use them — whole codebases, document sets, or long agent histories in one window.",
      },
      {
        title: "General chat and reasoning.",
        body: "Frontier-class MMLU and GPQA scores. A sensible default when a workload has not yet earned a specialist.",
      },
    ],
    benchmarks: [
      { name: "MMLU", score: "91.0", bar: 91 },
      { name: "GPQA Diamond", score: "90.9", bar: 90.9, note: "pass@1" },
      { name: "MMLU-Pro", score: "81.2", bar: 81.2 },
      {
        name: "DeepSWE v1.1",
        score: "74.2",
        bar: 74.2,
        note: "level with GPT-6 Astra and Opus 5",
      },
    ],
    benchmarksNote:
      "Published figures from DeepSeek and independent evaluations, October 2026.",
    specs: [
      { label: "Weights", value: "Open — deepseek-ai/DeepSeek-V4.1-Flash" },
      { label: "Released", value: "September 2026" },
      { label: "Quantization on Gradiated", value: "FP4" },
      { label: "Max output", value: "131K tokens" },
      { label: "Streaming", value: "Yes" },
      { label: "Tool calls", value: "Parallel tool calls, reasoning effort" },
    ],
    vitals: {
      input: "$0.30",
      cachedInput: "$0.006",
      output: "$1.20",
      context: "1M",
    },
    gettingStarted: {
      lede: "Point your existing client at our base URL and name the model. Your traffic starts accruing as traces — the raw material post-training is built from.",
      snippets: [
        {
          label: "Python — OpenAI SDK",
          code: `from openai import OpenAI
import os

client = OpenAI(
    base_url="https://api.gradiated.com",
    api_key=os.environ["GRADIATED_API_KEY"],
)

response = client.chat.completions.create(
    model="deepseek/deepseek-v4.1-flash",
    messages=[{"role": "user", "content": "Summarize this document."}],
)`,
        },
        {
          label: "curl",
          code: `curl https://api.gradiated.com/v1/chat/completions \\
  -H "Authorization: Bearer $GRADIATED_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "deepseek/deepseek-v4.1-flash",
    "messages": [{"role": "user", "content": "Summarize this document."}]
  }'`,
        },
      ],
      docsHref: "/docs/quickstart/",
      docsLabel: "Read the quickstart",
    },
  },
  {
    slug: "glm-5-3-flash",
    id: "z-ai/glm-5.3-flash",
    name: "GLM-5.3 Flash",
    maker: "Z.AI",
    mark: "GLM",
    icon: "/assets/models/zhipu-color.svg",
    oneLiner:
      "Z.AI's fast reasoning and tool-use model: near-frontier agentic scores at a fraction of frontier prices, with a million tokens of context.",
    tags: ["Open weights", "1M context", "320B-A18B MoE", "FP8 on Gradiated"],
    overview: [
      "GLM-5.3 Flash is the cost-optimised cut of Z.AI's GLM-5.3 line — a 320B mixture-of-experts that activates 18B parameters per token, built from a newly trained base rather than a distillation. The result is a model that reasons and uses tools like something much more expensive.",
      "Its distinguishing strength is multi-step work: terminal sessions, tool pipelines, automation flows. On automation benchmarks it leads models that cost ten times as much — which is exactly the shape of workload that benefits most from post-training on your own environment.",
    ],
    goodFor: [
      {
        title: "Agents and tool use.",
        body: "Near-frontier scores on terminal and tool-orchestration benchmarks. The strongest choice per dollar for multi-step agent loops.",
      },
      {
        title: "Automation workflows.",
        body: "Leads its benchmark set on multi-step automation — the repetitive, structured work where post-training pays back fastest.",
      },
      {
        title: "High-volume reasoning.",
        body: "Reasoning-model quality at $0.25 per million output tokens. Built for workloads where unit economics decide the architecture.",
      },
    ],
    benchmarks: [
      {
        name: "Terminal-Bench 2.1",
        score: "84.3",
        bar: 84.3,
        note: "Opus 4.8 scores 85.0",
      },
      { name: "Toolathlon Verified", score: "78.4", bar: 78.4 },
      { name: "DeepSWE v1.1", score: "63.4", bar: 63.4 },
      {
        name: "AutomationBench",
        score: "48.8",
        bar: 48.8,
        note: "leads Opus 4.8 at 41.0",
      },
      {
        name: "Humanity's Last Exam",
        score: "55.3",
        bar: 55.3,
        note: "with tools",
      },
    ],
    benchmarksNote:
      "Published figures from Z.AI and independent evaluations, October 2026.",
    specs: [
      { label: "Weights", value: "Open — zai-org/GLM-5.3-Flash" },
      { label: "Released", value: "August 2026" },
      { label: "Architecture", value: "320B MoE, 18B active" },
      { label: "Quantization on Gradiated", value: "FP8" },
      { label: "Max output", value: "131K tokens" },
      { label: "Streaming", value: "Yes" },
    ],
    vitals: {
      input: "$0.075",
      cachedInput: "$0.015",
      output: "$0.25",
      context: "1M",
    },
    gettingStarted: {
      lede: "Point your existing client at our base URL and name the model. Your traffic starts accruing as traces — the raw material post-training is built from.",
      snippets: [
        {
          label: "Python — OpenAI SDK",
          code: `from openai import OpenAI
import os

client = OpenAI(
    base_url="https://api.gradiated.com",
    api_key=os.environ["GRADIATED_API_KEY"],
)

response = client.chat.completions.create(
    model="z-ai/glm-5.3-flash",
    messages=[{"role": "user", "content": "Summarize this document."}],
)`,
        },
        {
          label: "curl",
          code: `curl https://api.gradiated.com/v1/chat/completions \\
  -H "Authorization: Bearer $GRADIATED_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "z-ai/glm-5.3-flash",
    "messages": [{"role": "user", "content": "Summarize this document."}]
  }'`,
        },
      ],
      docsHref: "/docs/quickstart/",
      docsLabel: "Read the quickstart",
    },
  },
  {
    slug: "kev-9b",
    id: "jaredpalmer/kev-9b",
    name: "Kev 9B",
    maker: "Jared Palmer",
    mark: "KEV",
    oneLiner:
      "A decision model, not a chat model: give it structured state and typed questions, get back calibrated choices, yes/no decisions and scores — no generated text, no output tokens to pay for.",
    tags: ["Open weights", "Apache-2.0", "Typed decisions", "Calibrated"],
    overview: [
      "Kev answers typed questions about structured state. Instead of generating prose it reads out probabilities — a choice among options you define, a yes/no decision, a score on a rubric — from a pointer head sitting on a Qwen3.5 base with a LoRA adapter. Each checkpoint ships with a fitted temperature, so the probabilities are calibrated out of the box.",
      "That shape makes it the model for the decisions scattered through a production system: routing, classification, guardrails, evals. The questions are typed, so there is no parsing step and no prompt-injection surface in the output — and because decisions generate no tokens, output is free. Kev 9B is the mid-size of an Apache-2.0 family that also ships 0.8B, 4B and 27B checkpoints you can run yourself.",
    ],
    goodFor: [
      {
        title: "Routing and classification.",
        body: "Choose a department, a priority, a pipeline branch — a typed choice with per-option probabilities, not text you have to parse.",
      },
      {
        title: "Guardrails and checks.",
        body: "Calibrated yes/no decisions over structured state. The fitted temperature cuts confident errors roughly in half against the raw head.",
      },
      {
        title: "Scoring and evals.",
        body: "Rubric scores with honest uncertainty, at $0.03 per million input tokens and nothing for output. Cheap enough to score everything.",
      },
    ],
    benchmarks: [
      {
        name: "Accuracy, in-distribution",
        score: "87.4%",
        bar: 87.4,
        note: "locked test set",
      },
      {
        name: "Accuracy, out-of-domain",
        score: "85.2%",
        bar: 85.2,
        note: "locked test set",
      },
      {
        name: "Calibration error",
        score: "0.042",
        note: "0.106 before the fitted temperature",
      },
      {
        name: "Confident errors",
        score: "4.0%",
        note: "8.7% before the fitted temperature",
      },
    ],
    benchmarksNote:
      "Published figures from the Kev release, September 2026. Decision accuracy is not comparable with generative benchmarks.",
    specs: [
      { label: "Weights", value: "Open — jaredpalmer/kev-9b, Apache-2.0" },
      { label: "Released", value: "September 2026" },
      { label: "Base", value: "Qwen3.5-9B-Base + LoRA + pointer head" },
      { label: "Family", value: "0.8B · 4B · 9B · 27B" },
      { label: "Precision on Gradiated", value: "BF16" },
      { label: "Output", value: "Decisions only — no generated text" },
    ],
    vitals: {
      input: "$0.03",
      cachedInput: "$0.006",
      output: "$0.00",
      context: "8.2K",
    },
    gettingStarted: {
      lede: "Kev speaks the System One API rather than chat completions: send state and named, typed questions through the TypeSafe SDK, pointed at our base URL.",
      snippets: [
        {
          label: "Python — TypeSafe SDK",
          code: `import os
from typesafe_sdk import Choice, TypeSafeClient

with TypeSafeClient(
    base_url="https://api.gradiated.com",
    api_key=os.environ["GRADIATED_API_KEY"],
    model="jaredpalmer/kev-9b",
) as client:
    response = client.system_one(
        state={"ticket": "I was charged twice. Please fix this today."},
        questions={
            "category": Choice(
                instructions="Choose the department for this ticket.",
                criteria={
                    "billing": "Charges or payments",
                    "technical": "Something is broken",
                    "other": "Anything else",
                },
            ),
        },
    )

print(response.choices["category"].choice)
print(response.choices["category"].probabilities)`,
        },
      ],
      docsHref: "/docs/systemone-sdk/",
      docsLabel: "Read the SystemOne SDK docs",
    },
  },
];

export const modelBySlug = (slug: string): ModelPageData | undefined =>
  models.find((model) => model.slug === slug);
