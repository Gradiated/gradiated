import { z } from "zod";

import { QWEN_PLACEHOLDER_PRICING } from "@gradiated/contracts/model-catalog";
import { EvaluationResultsSchema } from "@gradiated/contracts";

export const predictionsSchema = EvaluationResultsSchema;

type Pair = z.infer<typeof predictionsSchema>[number];
const outcome = (row: Pair) => {
  if ("judgment" in row) {
    if (row.judgment === "TIE") return "tie";
    if (row.judgment !== "A" && row.judgment !== "B") return "unresolved";

    return (row.judgment === "A") === row.fine_tuned_first ? "win" : "loss";
  }

  const [first, second] = row.judgments;
  if (first === "A" && second === "B") return "win";
  if (first === "B" && second === "A") return "loss";
  if (first === "TIE" && second === "TIE") return "tie";

  return "unresolved";
};

export const summarizePredictions = (
  rows: z.infer<typeof predictionsSchema>,
) => {
  const groups = new Map<
    string,
    {
      win: number;
      tie: number;
      loss: number;
      unresolved: number;
      count: number;
    }
  >();
  let fineTokens = 0,
    fineSeconds = 0,
    comparisonTokens = 0,
    comparisonSeconds = 0;

  for (const row of rows) {
    const counts = groups.get(row.group) ?? {
      win: 0,
      tie: 0,
      loss: 0,
      unresolved: 0,
      count: 0,
    };
    counts[outcome(row)]++;
    counts.count++;
    groups.set(row.group, counts);
    fineTokens += row.fine_tuned.tokens;
    fineSeconds += row.fine_tuned.seconds;
    comparisonTokens += row.comparison.tokens;
    comparisonSeconds += row.comparison.seconds;
  }

  const fractions = { win: 0, tie: 0, loss: 0, unresolved: 0 };
  for (const group of groups.values())
    for (const key of ["win", "tie", "loss", "unresolved"] as const)
      fractions[key] += group[key] / group.count / groups.size;

  const resolved = fractions.win + fractions.tie + fractions.loss;

  return {
    judging_method: rows.every((row) => "judgment" in row)
      ? ("randomized_single" as const)
      : ("both_orders" as const),
    holdout_groups: groups.size,
    holdout_examples: rows.length,
    fractions: {
      win: resolved ? fractions.win / resolved : 0,
      tie: resolved ? fractions.tie / resolved : 0,
      loss: resolved ? fractions.loss / resolved : 0,
      unresolved: Math.min(1, Math.max(0, fractions.unresolved)),
    },
    output_tokens_per_second: {
      fine_tuned: fineTokens / fineSeconds,
      comparison: comparisonTokens / comparisonSeconds,
    },
  };
};

export const estimateOutputCost = (
  rows: z.infer<typeof predictionsSchema>,
  baseModelId: string,
  comparisonModelId: string,
) => {
  if (
    rows.length === 0 ||
    baseModelId !== QWEN_PLACEHOLDER_PRICING.model_id ||
    comparisonModelId !== QWEN_PLACEHOLDER_PRICING.model_id
  )
    return null;

  const cost = (arm: "fine_tuned" | "comparison") => {
    const total =
      rows.reduce((sum, row) => sum + BigInt(row[arm].tokens), 0n) *
      BigInt(QWEN_PLACEHOLDER_PRICING.output_nano_usd_per_token);
    const count = BigInt(rows.length);

    return Number((total + count / 2n) / count);
  };

  return { fine_tuned: cost("fine_tuned"), comparison: cost("comparison") };
};
