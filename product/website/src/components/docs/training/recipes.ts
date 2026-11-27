import type { RecipeKind, SdkLanguage } from "./data";

export type RecipeInfo = {
  kind: RecipeKind;
  className: string;
  cli: string;
  title: string;
  href: string;
  name: string;
  model: string | null;
  why: string;
  record: string;
};

/* Record shapes are the ones each recipe guide documents. */
export const RECIPES: Record<RecipeKind, RecipeInfo> = {
  router: {
    kind: "router",
    className: "RouterRecipe",
    cli: "router",
    title: "Model router",
    href: "/docs/training/recipes/router/",
    name: "support-router",
    model: null,
    why: "Learns which prompts a cheaper model already handles, and sends only the rest to the expensive one.",
    record: `{"messages": [
  {"role": "user", "content": "Reset my password"},
  {"role": "assistant", "content": "Open Settings, then Security..."}],
 "metadata": {"model": "qwen/qwen3-8b"},
 "scores": {"resolved": 1.0}}`,
  },
  decision: {
    kind: "decision",
    className: "DecisionModelRecipe",
    cli: "decision-model",
    title: "Decision models",
    href: "/docs/training/recipes/decision-model/",
    name: "ticket-triage",
    model: "qwen/qwen3-0.6b",
    why: "Trains a small model to answer fixed-format questions (Choice, Noul, Score) about a state object.",
    record: `{"state": {"ticket": "I was charged twice. Please fix this today."},
 "questions": {"category": {"type": "choice",
   "criteria": {"billing": "Charges or payments", "other": "Anything else"}}},
 "expected_output": {"category": "billing"}}`,
  },
  sft: {
    kind: "sft",
    className: "SFTRecipe",
    cli: "sft",
    title: "Supervised fine-tuning",
    href: "/docs/training/recipes/sft/",
    name: "support-sft",
    model: "qwen/qwen3-8b",
    why: "Teaches a model to write outputs like your best examples. The last assistant turn is the target.",
    record: `{"messages": [
  {"role": "user", "content": "Count active users from yesterday."},
  {"role": "assistant", "content": "SELECT count(*) FROM users WHERE ..."}]}`,
  },
  dpo: {
    kind: "dpo",
    className: "DPORecipe",
    cli: "dpo",
    title: "Preference tuning (DPO)",
    href: "/docs/training/recipes/dpo/",
    name: "support-dpo",
    model: "qwen/qwen3-8b",
    why: "Pushes a model toward the answer people preferred and away from the one they rejected.",
    record: `{"prompt": [{"role": "user", "content": "Summarise this ticket"}],
 "chosen": [{"role": "assistant", "content": "Customer was double-charged..."}],
 "rejected": [{"role": "assistant", "content": "The ticket is about billing."}]}`,
  },
  distill: {
    kind: "distill",
    className: "DistillRecipe",
    cli: "distill",
    title: "Model distillation",
    href: "/docs/training/recipes/distillation/",
    name: "support-distill",
    model: "qwen/qwen3-4b",
    why: "A small student writes answers and a larger teacher grades every token, so the student copies the teacher on your prompts.",
    record: `{"messages": [{"role": "user", "content": "Explain our refund policy"}]}`,
  },
  cartridge: {
    kind: "cartridge",
    className: "CartridgeRecipe",
    cli: "cartridge",
    title: "Context Cartridges",
    href: "/docs/training/recipes/cartridges/",
    name: "api-docs-cartridge",
    model: "qwen/qwen3-8b",
    why: "Compresses a long, static context into a small trained prefix, so you stop sending it with every request.",
    record: `{"messages": [{"role": "user", "content": "Which endpoint lists invoices?"}]}`,
  },
  embedding: {
    kind: "embedding",
    className: "EmbeddingRecipe",
    cli: "embedding",
    title: "Embeddings",
    href: "/docs/training/recipes/embeddings/",
    name: "docs-embedder",
    model: null,
    why: "Fine-tunes a small encoder so your queries land next to the documents that answer them.",
    record: `{"query": "rotate an API key",
 "positive": "Keys: revoke the old key, then create one with the same scopes...",
 "negatives": ["Billing: invoices are issued monthly..."]}`,
  },
  reward: {
    kind: "reward",
    className: "RewardModelRecipe",
    cli: "reward-model",
    title: "Reward models",
    href: "/docs/training/recipes/reward-models/",
    name: "sql-verifier",
    model: "qwen/qwen3-8b",
    why: "Trains a scorer that ranks answers the way your preference pairs do, to grade outputs without a judge call.",
    record: `{"prompt": [{"role": "user", "content": "Monthly revenue by plan"}],
 "chosen": [{"role": "assistant", "content": "SELECT plan, sum(amount_usd) ..."}],
 "rejected": [{"role": "assistant", "content": "SELECT * FROM invoices"}]}`,
  },
};

const pyArgs: Record<RecipeKind, string> = {
  router: "",
  decision: 'model="qwen/qwen3-0.6b"',
  sft: 'model="qwen/qwen3-8b"',
  dpo: 'model="qwen/qwen3-8b"',
  distill: 'model="qwen/qwen3-4b", teacher="qwen/qwen3-14b"',
  cartridge:
    'model="qwen/qwen3-8b", context=Context.from_file("./api-docs.md")',
  embedding: "",
  reward: 'model="qwen/qwen3-8b"',
};

const tsCall: Record<RecipeKind, string> = {
  router: "recipes.router()",
  decision: 'recipes.decisionModel({ model: "qwen/qwen3-0.6b" })',
  sft: 'recipes.sft({ model: "qwen/qwen3-8b" })',
  dpo: 'recipes.dpo({ model: "qwen/qwen3-8b" })',
  distill:
    'recipes.distill({ model: "qwen/qwen3-4b", teacher: "qwen/qwen3-14b" })',
  cartridge: `recipes.cartridge({
      model: "qwen/qwen3-8b",
      context: Context.fromFile("./api-docs.md"),
    })`,
  embedding: "recipes.embedding()",
  reward: 'recipes.rewardModel({ model: "qwen/qwen3-8b" })',
};

const goRecipe: Record<RecipeKind, string> = {
  router: "grad.RouterRecipe{}",
  decision:
    'grad.DecisionModelRecipe{Common: grad.Common{Model: "qwen/qwen3-0.6b"}}',
  sft: 'grad.SFTRecipe{Common: grad.Common{Model: "qwen/qwen3-8b"}}',
  dpo: 'grad.DPORecipe{Common: grad.Common{Model: "qwen/qwen3-8b"}}',
  distill: `grad.DistillRecipe{
		Common:  grad.Common{Model: "qwen/qwen3-4b"},
		Teacher: "qwen/qwen3-14b",
	}`,
  cartridge: `grad.CartridgeRecipe{
		Common:  grad.Common{Model: "qwen/qwen3-8b"},
		Context: grad.ContextFromFile("./api-docs.md"),
	}`,
  embedding: "grad.EmbeddingRecipe{}",
  reward: 'grad.RewardModelRecipe{Common: grad.Common{Model: "qwen/qwen3-8b"}}',
};

const rustVariant: Record<RecipeKind, string> = {
  router: "Router",
  decision: "Decision",
  sft: "Sft",
  dpo: "Dpo",
  distill: "Distill",
  cartridge: "Cartridge",
  embedding: "Embedding",
  reward: "Reward",
};

const rustRecipe = (info: RecipeInfo): string => {
  const base = `RecipeSpec::new(RecipeKind::${rustVariant[info.kind]})${info.model ? `.model("${info.model}")` : ""}`;

  if (info.kind === "distill") {
    return `RecipeSpec {
    teacher: Some("qwen/qwen3-14b".into()),
    ..${base}
};`;
  }
  if (info.kind === "cartridge") {
    return `RecipeSpec {
    context_text: Some(std::fs::read_to_string("./api-docs.md")?),
    ..${base}
};`;
  }
  return `${base};`;
};

const cliFlags = (info: RecipeInfo): string => {
  const flags = [`--recipe ${info.cli}`];
  if (info.model) flags.push(`--model ${info.model}`);
  if (info.kind === "distill") flags.push("--teacher qwen/qwen3-14b");
  if (info.kind === "cartridge") flags.push("--context-file ./api-docs.md");
  return flags.join(" ");
};

export const recipeSnippet = (
  kind: RecipeKind,
  language: SdkLanguage,
  dataset = "support-prod",
): { code: string; lang: string } => {
  const info = RECIPES[kind];
  const out = `./${info.name}`;

  switch (language) {
    case "Python": {
      const imports =
        kind === "cartridge"
          ? "from grad import Context, Grad"
          : "from grad import Grad";
      return {
        lang: "python",
        code: `${imports}
from grad.recipes import ${info.className}

client = Grad()
run = client.runs.create(
    dataset=client.datasets.get("${dataset}"),
    name="${info.name}",
    recipe=${info.className}(${pyArgs[kind]}),
    max_cost_usd=20,
).wait()
run.download("${out}")`,
      };
    }
    case "TypeScript": {
      const imports =
        kind === "cartridge" ? "Context, Grad, recipes" : "Grad, recipes";
      return {
        lang: "typescript",
        code: `import { ${imports} } from "@gradiated/grad";

const grad = new Grad();
const run = await grad.runs
  .create({
    dataset: await grad.datasets.get("${dataset}"),
    name: "${info.name}",
    recipe: ${tsCall[kind]},
    maxCostUsd: 20,
  })
  .wait();
await run.download("${out}");`,
      };
    }
    case "Go":
      return {
        lang: "go",
        code: `client := grad.NewClient()
dataset, err := client.Datasets.Get(ctx, "${dataset}")
if err != nil {
	log.Fatal(err)
}
run, err := client.Runs.Create(ctx, grad.RunParams{
	Dataset:    dataset,
	Name:       "${info.name}",
	Recipe:     ${goRecipe[kind]},
	MaxCostUSD: 20,
}).Wait(ctx)
if err != nil {
	log.Fatal(err)
}
_, _ = run.Download(ctx, "${out}")`,
      };
    case "Rust":
      return {
        lang: "rust",
        code: `use grad_sdk::{Client, DownloadOptions, PlanRunRequest, RecipeKind, RecipeSpec, WaitOptions};

let client = Client::new();
let recipe = ${rustRecipe(info)}
let request = PlanRunRequest::new("${dataset}", "${info.name}", recipe).max_cost_usd(20.0);
let run = client.runs().create(&request, None).await?;
let run = client.runs().wait(&run.id, &WaitOptions::default()).await?;
client
    .artifacts()
    .download(&format!("{}@latest", run.name), &DownloadOptions::extract("${out}"))
    .await?;`,
      };
    case "CLI":
      return {
        lang: "bash",
        code: `grad train --dataset ${dataset} --name ${info.name} ${cliFlags(info)} --dry-run
grad train --dataset ${dataset} --name ${info.name} ${cliFlags(info)} --max-cost-usd 20 --wait
grad artifacts download ${info.name}@latest --output ${out}`,
      };
  }
};
