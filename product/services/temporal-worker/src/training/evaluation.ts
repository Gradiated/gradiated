import { z } from "zod";

import { QWEN_PLACEHOLDER_PRICING } from "@gradiated/contracts/model-catalog";
import { EvaluationResultsSchema } from "@gradiated/contracts";
import type {
  EvaluationPrice,
  EvaluationPricing,
} from "./evaluation-pricing.js";

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

const predictionTokenCost = (
  prediction: Pair["fine_tuned"],
  price: EvaluationPrice | null | undefined,
) => {
  const usage = prediction.usage;
  if (!usage || !price) return null;

  const tier = price.rates.overrides
    ?.filter((tier) => usage.input_tokens >= tier.min_prompt_tokens)
    .sort((a, b) => b.min_prompt_tokens - a.min_prompt_tokens)[0];
  const rates = {
    ...price.rates,
    ...tier,
    prompt: tier?.prompt ?? price.rates.prompt,
    completion: tier?.completion ?? price.rates.completion,
  };
  const read = usage.cached_input_tokens ?? 0;
  const write = usage.cache_write_tokens ?? 0;
  const prompt = usage.input_tokens - read - write;
  if (
    prompt < 0 ||
    (read > 0 && rates.input_cache_read === undefined) ||
    (write > 0 && rates.input_cache_write === undefined)
  )
    return null;

  const cost =
    (prompt * rates.prompt +
      usage.output_tokens * rates.completion +
      read * (rates.input_cache_read ?? 0) +
      write * (rates.input_cache_write ?? 0)) *
    1e9;

  return Number.isSafeInteger(Math.round(cost)) ? cost : null;
};

export const pricePredictions = (
  rows: z.infer<typeof predictionsSchema>,
  pricing: EvaluationPricing | undefined,
  placeholderOutputOnly: boolean,
) => {
  const price = (
    prediction: Pair["fine_tuned"],
    arm: "fine_tuned" | "comparison",
  ) => {
    const cost = placeholderOutputOnly
      ? prediction.tokens * QWEN_PLACEHOLDER_PRICING.output_nano_usd_per_token
      : predictionTokenCost(prediction, pricing?.[arm]);

    return cost === null || !Number.isSafeInteger(Math.round(cost))
      ? prediction
      : { ...prediction, cost_nano_usd: Math.round(cost) };
  };

  return rows.map((row) => ({
    ...row,
    fine_tuned: price(row.fine_tuned, "fine_tuned"),
    comparison: price(row.comparison, "comparison"),
  }));
};

export const estimateTokenCost = (
  rows: z.infer<typeof predictionsSchema>,
  pricing: EvaluationPricing,
) => {
  if (!rows.length || !pricing.fine_tuned || !pricing.comparison) return null;

  const cost = (arm: "fine_tuned" | "comparison", price: EvaluationPrice) => {
    let total = 0;
    for (const row of rows) {
      const value = predictionTokenCost(row[arm], price);
      if (value === null) return null;

      total += value;
    }

    const mean = Math.round(total / rows.length);

    return Number.isSafeInteger(mean) ? mean : null;
  };
  const fine_tuned = cost("fine_tuned", pricing.fine_tuned);
  const comparison = cost("comparison", pricing.comparison);

  return fine_tuned === null || comparison === null
    ? null
    : { fine_tuned, comparison };
};
