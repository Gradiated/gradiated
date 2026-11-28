import type { ComponentType } from "react";

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
import DocsCliReference from "../docs/reference/cli.mdx";
import DocsPrimitivesReference from "../docs/reference/primitives.mdx";
import DocsTrainingApiReference from "../docs/reference/training-api.mdx";
import DocsTrainingParametersReference from "../docs/reference/training-parameters.mdx";
import DocsServiceTiers from "../docs/service-tiers.mdx";
import DocsSystemOneSdk from "../docs/systemone-sdk.mdx";
import DocsTrainingAdvancedObjectives from "../docs/training/advanced-objectives.mdx";
import DocsTrainingArtifacts from "../docs/training/artifacts.mdx";
import DocsTrainingChangelog from "../docs/training/changelog.mdx";
import DocsTrainingCustomLoops from "../docs/training/custom-loops.mdx";
import DocsTrainingDeploying from "../docs/training/deploying.mdx";
import DocsTrainingEnvironments from "../docs/training/environments.mdx";
import DocsTrainingErrors from "../docs/training/errors.mdx";
import DocsTrainingEvaluations from "../docs/training/evaluations.mdx";
import DocsTrainingModels from "../docs/training/models.mdx";
import DocsTrainingObservability from "../docs/training/observability.mdx";
import DocsTrainingOverview from "../docs/training/index.mdx";
import DocsTrainingRecipes from "../docs/training/recipes.mdx";
import DocsTrainingRubrics from "../docs/training/rubrics.mdx";
import DocsTrainingSelfHosting from "../docs/training/self-hosting.mdx";
import DocsTrainingTuningTroubleshooting from "../docs/training/tuning-troubleshooting.mdx";
import DocsRecipeCartridges from "../docs/training/recipes/cartridges.mdx";
import DocsRecipeDecisionModel from "../docs/training/recipes/decision-model.mdx";
import DocsRecipeDistillation from "../docs/training/recipes/distillation.mdx";
import DocsRecipeDpo from "../docs/training/recipes/dpo.mdx";
import DocsRecipeEmbeddings from "../docs/training/recipes/embeddings.mdx";
import DocsRecipeRewardModels from "../docs/training/recipes/reward-models.mdx";
import DocsRecipeRlAgents from "../docs/training/recipes/rl-agents.mdx";
import DocsRecipeRouter from "../docs/training/recipes/router.mdx";
import DocsRecipeSft from "../docs/training/recipes/sft.mdx";
import DocsRecipeTracesToEnvironments from "../docs/training/recipes/traces-to-environments.mdx";
import DocsTrainingTrajectories from "../docs/training/trajectories.mdx";
import DocsIntegrationsOverview from "../docs/training/integrations/index.mdx";
import DocsIntegrationLangfuse from "../docs/training/integrations/langfuse.mdx";
import DocsIntegrationLangSmith from "../docs/training/integrations/langsmith.mdx";
import DocsIntegrationBraintrust from "../docs/training/integrations/braintrust.mdx";
import DocsIntegrationPostHog from "../docs/training/integrations/posthog.mdx";
import DocsIntegrationPhoenix from "../docs/training/integrations/phoenix.mdx";

type DocsDocument = {
  title: string;
  path: string;
  Component: ComponentType<Record<string, unknown>>;
  /** Reference pages whose samples sit beside the text need the room. */
  wide?: boolean;
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
    title: "Trajectories",
    path: "/docs/training/trajectories/",
    Component: DocsTrainingTrajectories,
  },
  "training-recipes": {
    title: "Recipes",
    path: "/docs/training/recipes/",
    Component: DocsTrainingRecipes,
  },
  "training-rubrics": {
    title: "Rubrics",
    path: "/docs/training/rubrics/",
    Component: DocsTrainingRubrics,
  },
  "training-environments": {
    title: "Environments (soon)",
    path: "/docs/training/environments/",
    Component: DocsTrainingEnvironments,
  },
  "training-evaluations": {
    title: "Evaluations",
    path: "/docs/training/evaluations/",
    Component: DocsTrainingEvaluations,
  },
  "training-artifacts": {
    title: "Artifacts",
    path: "/docs/training/artifacts/",
    Component: DocsTrainingArtifacts,
  },
  "training-deploying": {
    title: "Deploying",
    path: "/docs/training/deploying/",
    Component: DocsTrainingDeploying,
  },
  "training-models": {
    title: "Supported models",
    path: "/docs/training/models/",
    Component: DocsTrainingModels,
  },
  "training-custom-loops": {
    title: "Custom loops (soon)",
    path: "/docs/training/custom-loops/",
    Component: DocsTrainingCustomLoops,
  },
  "training-advanced-objectives": {
    title: "Advanced objectives (soon)",
    path: "/docs/training/advanced-objectives/",
    Component: DocsTrainingAdvancedObjectives,
  },
  "training-tuning-troubleshooting": {
    title: "Tuning & troubleshooting",
    path: "/docs/training/tuning-troubleshooting/",
    Component: DocsTrainingTuningTroubleshooting,
  },
  "training-self-hosting": {
    title: "Self-hosting",
    path: "/docs/training/self-hosting/",
    Component: DocsTrainingSelfHosting,
  },
  "training-observability": {
    title: "Observability",
    path: "/docs/training/observability/",
    Component: DocsTrainingObservability,
  },
  "training-errors": {
    title: "Errors",
    path: "/docs/training/errors/",
    Component: DocsTrainingErrors,
  },
  "training-changelog": {
    title: "Changelog",
    path: "/docs/training/changelog/",
    Component: DocsTrainingChangelog,
  },
  "recipe-router": {
    title: "Model router",
    path: "/docs/training/recipes/router/",
    Component: DocsRecipeRouter,
  },
  "recipe-decision-model": {
    title: "Decision models",
    path: "/docs/training/recipes/decision-model/",
    Component: DocsRecipeDecisionModel,
  },
  "recipe-sft": {
    title: "Supervised fine-tuning (SFT)",
    path: "/docs/training/recipes/sft/",
    Component: DocsRecipeSft,
  },
  "recipe-dpo": {
    title: "Preference tuning (DPO)",
    path: "/docs/training/recipes/dpo/",
    Component: DocsRecipeDpo,
  },
  "recipe-rl-agents": {
    title: "RL for agents (soon)",
    path: "/docs/training/recipes/rl-agents/",
    Component: DocsRecipeRlAgents,
  },
  "recipe-traces-to-environments": {
    title: "Traces to environments (soon)",
    path: "/docs/training/recipes/traces-to-environments/",
    Component: DocsRecipeTracesToEnvironments,
  },
  "recipe-distillation": {
    title: "Model distillation",
    path: "/docs/training/recipes/distillation/",
    Component: DocsRecipeDistillation,
  },
  "recipe-cartridges": {
    title: "Context Cartridges",
    path: "/docs/training/recipes/cartridges/",
    Component: DocsRecipeCartridges,
  },
  "recipe-reward-models": {
    title: "Reward models",
    path: "/docs/training/recipes/reward-models/",
    Component: DocsRecipeRewardModels,
  },
  "recipe-embeddings": {
    title: "Embeddings",
    path: "/docs/training/recipes/embeddings/",
    Component: DocsRecipeEmbeddings,
  },
  "integrations-overview": {
    title: "Integrations",
    path: "/docs/training/integrations/",
    Component: DocsIntegrationsOverview,
  },
  "integration-langfuse": {
    title: "Langfuse",
    path: "/docs/training/integrations/langfuse/",
    Component: DocsIntegrationLangfuse,
  },
  "integration-langsmith": {
    title: "LangSmith",
    path: "/docs/training/integrations/langsmith/",
    Component: DocsIntegrationLangSmith,
  },
  "integration-braintrust": {
    title: "Braintrust",
    path: "/docs/training/integrations/braintrust/",
    Component: DocsIntegrationBraintrust,
  },
  "integration-posthog": {
    title: "PostHog",
    path: "/docs/training/integrations/posthog/",
    Component: DocsIntegrationPostHog,
  },
  "integration-phoenix": {
    title: "Arize Phoenix",
    path: "/docs/training/integrations/phoenix/",
    Component: DocsIntegrationPhoenix,
  },
  "api-reference": {
    title: "API reference",
    path: "/docs/api-reference/",
    Component: DocsApiReference,
  },
  "training-api-reference": {
    title: "Training API",
    path: "/docs/reference/training-api/",
    Component: DocsTrainingApiReference,
    wide: true,
  },
  "primitives-reference": {
    title: "Primitives reference",
    path: "/docs/reference/primitives/",
    Component: DocsPrimitivesReference,
  },
  "training-parameters-reference": {
    title: "Training parameters",
    path: "/docs/reference/training-parameters/",
    Component: DocsTrainingParametersReference,
  },
  "cli-reference": {
    title: "CLI reference",
    path: "/docs/reference/cli/",
    Component: DocsCliReference,
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
      "training-rubrics",
      "training-environments",
      "training-evaluations",
      "training-artifacts",
      "training-deploying",
      "training-models",
    ],
  },
  {
    heading: "Recipe guides",
    items: [
      "recipe-router",
      "recipe-decision-model",
      "recipe-sft",
      "recipe-dpo",
      "recipe-rl-agents",
      "recipe-traces-to-environments",
      "recipe-distillation",
      "recipe-cartridges",
      "recipe-reward-models",
      "recipe-embeddings",
    ],
  },
  {
    heading: "Trace integrations",
    items: [
      "integrations-overview",
      "integration-langfuse",
      "integration-langsmith",
      "integration-braintrust",
      "integration-posthog",
      "integration-phoenix",
    ],
  },
  {
    heading: "Advanced",
    items: [
      "training-custom-loops",
      "training-advanced-objectives",
      "training-tuning-troubleshooting",
      "training-errors",
      "training-self-hosting",
      "training-observability",
    ],
  },
  { heading: "Integrations", items: ["opencode", "codex", "claude-code"] },
  {
    heading: "Reference",
    items: [
      "api-reference",
      "training-api-reference",
      "primitives-reference",
      "training-parameters-reference",
      "cli-reference",
      "training-changelog",
    ],
  },
];

export const legacyPaths: Record<string, string> = {
  "/docs/api/": documents["api-reference"].path,
  "/docs/api-keys/": documents.quickstart.path,
  "/docs/billing/": documents.errors.path,
  "/docs/migrate/": documents.quickstart.path,
  "/docs/streaming/": documents["openai-sdk"].path,
  "/docs/tool-calling/": documents["openai-sdk"].path,
  "/docs/training/endpoints/": documents["training-deploying"].path,
  "/docs/training/recipes/classifier/": documents["recipe-decision-model"].path,
  "/docs/training/recipes/sft-dpo/": documents["recipe-sft"].path,
  "/docs/training/traces-to-environments/":
    documents["recipe-traces-to-environments"].path,
  "/docs/usage/": documents.index.path,
};

export const markdownPathFor = (path: string): string =>
  path === "/docs/" ? "/docs/index.md" : `${path.replace(/\/$/, "")}.md`;
