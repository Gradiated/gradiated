import { z } from "zod";

import { RECIPE_LABEL } from "@/lib/grad/labels";
import type {
  PlanRunRequest,
  RecipeKind,
  TrainableModel,
} from "@/lib/grad/types";
import { DATASET_NAME_PATTERN } from "@/lib/grad/upload";

export const RECIPE_OPTIONS = [
  {
    value: "sft",
    label: RECIPE_LABEL.sft,
    description: "Supervised fine-tuning on chat transcripts.",
  },
  {
    value: "dpo",
    label: RECIPE_LABEL.dpo,
    description: "Preference tuning on chosen and rejected answers.",
  },
  {
    value: "distill",
    label: RECIPE_LABEL.distill,
    description: "Teach a small model to answer like a larger teacher.",
  },
  {
    value: "router",
    label: RECIPE_LABEL.router,
    description: "Route each request to the cheapest model that answers well.",
  },
  {
    value: "decision",
    label: RECIPE_LABEL.decision,
    description: "Classification and scoring heads on a frozen model.",
  },
  {
    value: "cartridge",
    label: RECIPE_LABEL.cartridge,
    description: "Compress a long context into a reusable prefix.",
  },
  {
    value: "embedding",
    label: RECIPE_LABEL.embedding,
    description: "Retrieval embeddings from query and passage pairs.",
  },
  {
    value: "reward",
    label: RECIPE_LABEL.reward,
    description: "A reward model from preference pairs or scores.",
  },
] as const satisfies readonly {
  value: Exclude<RecipeKind, "grpo">;
  label: string;
  description: string;
}[];

export type FormRecipeKind = (typeof RECIPE_OPTIONS)[number]["value"];

const FORM_RECIPE_KINDS = [
  "sft",
  "dpo",
  "distill",
  "router",
  "decision",
  "cartridge",
  "embedding",
  "reward",
] as const satisfies readonly FormRecipeKind[];

export const DEFAULT_MODEL = "default";

const optionalText = z.string().trim().max(200_000);

export const runFormSchema = z.object({
  dataset: z.string().regex(DATASET_NAME_PATTERN, "Choose a dataset."),
  kind: z.enum(FORM_RECIPE_KINDS),
  model: z.string().min(1),
  name: z
    .string()
    .trim()
    .regex(
      DATASET_NAME_PATTERN,
      "Use lowercase letters, digits, '.', '_' and '-', starting with a letter or digit.",
    ),
  maxCostUsd: z
    .string()
    .trim()
    .refine(
      (value) => value === "" || Number(value) > 0,
      "Enter an amount above zero, or leave it empty.",
    ),
  teacher: optionalText,
  contextText: optionalText,
  candidates: optionalText,
  rubric: optionalText,
});

export type RunForm = z.infer<typeof runFormSchema>;

export const defaultRunForm = (dataset = ""): RunForm => ({
  dataset,
  kind: "sft",
  model: DEFAULT_MODEL,
  name: dataset ? `${dataset}-sft` : "",
  maxCostUsd: "",
  teacher: "",
  contextText: "",
  candidates: "",
  rubric: "",
});

export const usesTeacher = (kind: FormRecipeKind) =>
  kind === "distill" || kind === "cartridge";

export const runRequest = (form: RunForm): PlanRunRequest => {
  const candidates = form.candidates
    .split(/[\s,]+/)
    .map((model) => model.trim())
    .filter(Boolean);

  return {
    dataset: form.dataset,
    name: form.name.trim(),
    recipe: {
      kind: form.kind,
      ...(form.model !== DEFAULT_MODEL ? { model: form.model } : {}),
      ...(usesTeacher(form.kind) && form.teacher
        ? { teacher: form.teacher }
        : {}),
      ...(form.kind === "cartridge" && form.contextText
        ? { contextText: form.contextText }
        : {}),
      ...(form.kind === "router" && candidates.length
        ? { models: candidates }
        : {}),
      ...(form.kind === "router" && form.rubric ? { rubric: form.rubric } : {}),
    },
    ...(form.maxCostUsd ? { maxCostUsd: Number(form.maxCostUsd) } : {}),
  };
};

export const modelsForRecipe = (
  models: readonly TrainableModel[],
  kind: RecipeKind,
) => models.filter((model) => model.recipes.includes(kind));

export const defaultModelFor = (
  models: readonly TrainableModel[],
  kind: RecipeKind,
) => models.find((model) => model.defaultFor.includes(kind))?.id;
