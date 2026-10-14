import { createHash } from "node:crypto";
import { Context } from "@temporalio/activity";
import { z } from "zod";
import {
  trainingRecipeForModel,
  RunDatasetSummarySchema,
  TrainingRunEventPayloadSchema,
  type RunEvaluation,
} from "@gradiated/contracts";
import {
  buildSftDataset,
  createTrainingRunStore,
  trainingNodes,
  prepareTraining,
  validateSftInput,
  TrainingAdmissionError,
  ControlServiceError,
  type TrainingEngine,
  type TrainingArtifacts,
  type TrainingArtifact,
  type ControlDatabase,
  type ContentStore,
  type TrainingInput,
} from "@gradiated/control";
import type { KubernetesRequest } from "./kubernetes-host.js";
import {
  createTrainingHosts,
  type TrainingHost,
  type TrainingHostConfig,
} from "./kubernetes-host.js";

import {
  estimateOutputCost,
  estimateTokenCost,
  predictionsSchema,
  pricePredictions,
  summarizePredictions,
} from "./evaluation.js";

import { evaluatePairs } from "./evaluate-pairs.js";
import { predictionSchema, type EvaluationModel } from "./evaluation-models.js";
import {
  evaluationPricingSchema,
  type EvaluationPricing,
  type createEvaluationPricing,
} from "./evaluation-pricing.js";

import { persistTrainingDataset } from "./dataset.js";

const artifactSchema = z.object({
  key: z.string(),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
  size_bytes: z
    .number()
    .int()
    .positive()
    .max(256 * 1024 * 1024),
});
const datasetSchema = z.object({
  train: artifactSchema,
  validation: artifactSchema,
  evaluation: artifactSchema,
  host: z.object({
    bundleUrl: z.string(),
    bundleSha256: z.string(),
    baseId: z.string(),
    gpuType: z.string(),
    nodePool: z.string().optional(),
    recipe: z.record(z.string(), z.unknown()).optional(),
  }),
  recipe: z.looseObject({
    id: z.string(),
    model: z.string(),
    revision: z.string(),
    max_steps: z.number().int().positive(),
    checkpoint_steps: z.number().int().positive(),
    rank: z.number().int().positive(),
    early_stopping: z
      .object({
        patience: z.number().int().positive(),
        threshold: z.number().nonnegative(),
        min_steps: z.number().int().nonnegative(),
      })
      .optional(),
    validation_examples: z.number().int().positive().optional(),
    shuffle: z.boolean().optional(),
    lr_scheduler_type: z.enum(["cosine", "linear", "constant"]).optional(),
    warmup_steps: z.number().int().nonnegative().optional(),
  }),
});
const pollSchema = z.object({
  status: z.enum(["running", "complete", "failed"]),
  events: z.array(z.unknown()).max(100),
  next: z.number().int(),
  total: z.number().int(),
  result: z.unknown(),
});
const heartbeat = async <T>(operation: () => Promise<T>) => {
  const context = Context.current();
  const timer = setInterval(() => context.heartbeat(), 5000);
  try {
    context.cancellationSignal.throwIfAborted();
    context.heartbeat();
    const result = await operation();
    context.cancellationSignal.throwIfAborted();
    return result;
  } finally {
    clearInterval(timer);
  }
};

export const createTrainingExecutorActivities = (options: {
  database: ControlDatabase;
  engine: TrainingEngine;
  contents: ContentStore;
  artifacts: TrainingArtifacts;
  request: KubernetesRequest;
  podIds: string[];
  host: TrainingHostConfig;
  evaluationModels?: EvaluationModel;
  evaluationPricing?: ReturnType<typeof createEvaluationPricing>;
}) => {
  const { database, artifacts } = options;
  const store = createTrainingRunStore(database);
  const hosts = createTrainingHosts({
    request: options.request,
    nodes: () => trainingNodes(database, options.podIds),
    config: options.host,
    signal: () => Context.current().cancellationSignal,
  });
  const json = async (key: string) =>
    JSON.parse(Buffer.from(await artifacts.read(key)).toString()) as unknown;
  const putJson = (key: string, value: unknown) =>
    artifacts.put(key, Buffer.from(JSON.stringify(value)));
  const scopedArtifact = (runId: string, value: unknown) => {
    const artifact = artifactSchema.parse(value);
    if (!artifact.key.startsWith(`runs/${runId}/`))
      throw new Error("Trainer returned an artifact outside the run.");
    return artifact;
  };
  const execute = async (
    runId: string,
    ordinal: number,
    host: TrainingHost,
    command: Record<string, unknown>,
  ) => {
    const id =
      typeof command.id === "string"
        ? command.id
        : `${String(command.operation)}-${ordinal}`;
    await hosts.call(host, "/operations", { ...command, id });
    let after = 0;
    for (;;) {
      Context.current().heartbeat({ after });
      const state = pollSchema.parse(
        await hosts.call(host, `/operations/${id}?after=${after}`),
      );
      const events = state.events.map((value) =>
        TrainingRunEventPayloadSchema.parse(value),
      );
      for (let index = 0; index < events.length; index++) {
        if (events[index]!.type !== "trainer_checkpoint") continue;
        const checkpoint = scopedArtifact(runId, state.events[index]);
        await artifacts.verify(checkpoint);
        await putJson(`runs/${runId}/checkpoints/latest.json`, checkpoint);
      }
      await store.appendTrainerEvents(runId, ordinal, events);
      after = state.next;
      if (after < state.total) continue;
      if (state.status === "failed") throw new Error("Trainer step failed.");
      if (state.status === "complete") return state.result;
      await Context.current().sleep(1000);
    }
  };
  const cachedArtifact = async (key: string) => {
    if (!(await artifacts.exists(key))) return null;
    const artifact = artifactSchema.parse(await json(key));
    await artifacts.verify(artifact);
    return artifact;
  };
  return {
    prepareTrainingRun: (taskId: string) =>
      heartbeat(async () => {
        try {
          return validateSftInput(
            await prepareTraining(
              database,
              options.contents,
              taskId,
              "automation",
              null,
              options.engine,
            ),
          );
        } catch (error) {
          if (
            error instanceof TrainingAdmissionError ||
            (error instanceof ControlServiceError && error.code === "not_found")
          )
            return null;
          throw error;
        }
      }),
    buildTrainingDataset: (runId: string, input: TrainingInput) =>
      heartbeat(async () => {
        const externalEvaluation =
          input.comparisonModelId !== input.baseModelId ||
          input.judgeModelId !== input.baseModelId;
        if (externalEvaluation) {
          if (!options.evaluationModels)
            throw new Error("Evaluation models are not configured.");
          for (const modelId of [input.comparisonModelId, input.judgeModelId]) {
            if (modelId !== input.baseModelId)
              await options.evaluationModels.check(modelId);
          }
        }

        const manifestKey = `runs/${runId}/run-manifest.json`;
        const exists = await artifacts.exists(manifestKey);
        let manifest: unknown;

        if (exists) {
          manifest = await json(manifestKey);
        } else {
          const dataset = await buildSftDataset(options.contents, input);
          const saved = await persistTrainingDataset(
            artifacts,
            `runs/${runId}/dataset/v1`,
            dataset,
            input.inputCutoff,
          );
          const recipe = trainingRecipeForModel(input.baseModelId);
          if (!recipe) throw new Error("Training recipe is unavailable.");
          manifest = {
            ...saved,
            host: { ...options.host, recipe },
            recipe,
          };
        }

        const saved = datasetSchema
          .extend({ summary: RunDatasetSummarySchema })
          .parse(manifest);

        if (!exists) await putJson(manifestKey, saved);
        await store.result(
          runId,
          "dataset",
          saved.summary,
          { type: "dataset_built", ...saved.summary },
          Context.current().info.attempt,
        );

        return datasetSchema.parse(saved);
      }),
    allocateTrainingHost: (
      runId: string,
      ordinal: number,
      config: TrainingHostConfig,
    ) => heartbeat(() => hosts.allocate(runId, ordinal, config)),
    renewTrainingHost: (host: TrainingHost) => hosts.renew(host),
    releaseTrainingHost: (runId: string) =>
      heartbeat(() => hosts.release(runId)),
    trainAdapter: (
      runId: string,
      ordinal: number,
      host: TrainingHost,
      dataset: z.infer<typeof datasetSchema>,
    ) =>
      heartbeat(async () => {
        const resultKey = `runs/${runId}/output/result.json`;
        const existing = await cachedArtifact(resultKey);
        if (existing) return existing;
        const checkpoint = await cachedArtifact(
          `runs/${runId}/checkpoints/latest.json`,
        );
        const checkpoints: Record<
          number,
          Awaited<ReturnType<TrainingArtifacts["upload"]>>
        > = {};
        for (
          let step = dataset.recipe.checkpoint_steps;
          step <= dataset.recipe.max_steps;
          step += dataset.recipe.checkpoint_steps
        ) {
          checkpoints[step] = await artifacts.upload(
            `runs/${runId}/checkpoints/${ordinal}/${step}.tar.gz`,
          );
        }

        const result = scopedArtifact(
          runId,
          await execute(runId, ordinal, host, {
            operation: "train",
            dataset: await artifacts.download(dataset.train),
            validation: await artifacts.download(dataset.validation),
            checkpoints,
            checkpoint: checkpoint
              ? await artifacts.download(checkpoint)
              : null,
            output: await artifacts.upload(
              `runs/${runId}/output/${ordinal}/adapter.tar.gz`,
            ),
          }),
        );
        await artifacts.verify(result);
        await putJson(resultKey, result);
        return result;
      }),
    verifyAdapter: (
      runId: string,
      ordinal: number,
      host: TrainingHost,
      adapter: TrainingArtifact,
    ) =>
      heartbeat(async () => {
        await artifacts.verify(adapter);
        const verified = z.object({
          verified: z.literal(true),
          sha256: z.literal(adapter.sha256),
        });
        verified.parse(
          await execute(runId, ordinal, host, {
            operation: "verify",
            adapter: await artifacts.download(adapter),
          }),
        );
      }),
    publishAdapter: (
      runId: string,
      input: TrainingInput,
      artifact: TrainingArtifact,
      rank: number,
    ) =>
      heartbeat(async () => {
        await artifacts.verify(artifact);
        const manifest = datasetSchema.parse(
          await json(`runs/${runId}/run-manifest.json`),
        );
        if (rank !== manifest.recipe.rank)
          throw new Error(
            "Adapter rank differs from the frozen training recipe.",
          );

        return store.publish(
          runId,
          input,
          {
            format: "peft_lora",
            artifact_uri: artifacts.uri(artifact.key),
            sha256: artifact.sha256,
            size_bytes: artifact.size_bytes,
            rank,
            base_model_revision: manifest.recipe.revision,
          },
          "available",
        );
      }),
    evaluateAdapter: (
      runId: string,
      ordinal: number,
      host: TrainingHost,
      input: TrainingInput,
      dataset: z.infer<typeof datasetSchema>,
      adapter: TrainingArtifact,
    ) =>
      heartbeat(async () => {
        const resultKey = `runs/${runId}/evaluation/result.json`;
        let artifact = await cachedArtifact(resultKey);
        if (!artifact) {
          artifact = scopedArtifact(
            runId,
            await execute(runId, ordinal, host, {
              operation: "generate",
              external_evaluation:
                input.comparisonModelId !== input.baseModelId ||
                input.judgeModelId !== input.baseModelId,
              adapter: await artifacts.download(adapter),
              dataset: await artifacts.download(dataset.evaluation),
              output: await artifacts.upload(
                `runs/${runId}/evaluation/${ordinal}/predictions.json`,
              ),
            }),
          );
          await artifacts.verify(artifact);
          if (
            input.comparisonModelId !== input.baseModelId ||
            input.judgeModelId !== input.baseModelId
          ) {
            if (!options.evaluationModels)
              throw new Error("Evaluation models are not configured.");
            const models: EvaluationModel = {
              check: options.evaluationModels.check,
              generate: (modelId, messages, signal) =>
                modelId === input.baseModelId
                  ? execute(runId, ordinal, host, {
                      operation: "predict",
                      id: `predict-${ordinal}-${createHash("sha256").update(JSON.stringify(messages)).digest("hex")}`,
                      messages,
                    }).then((value) => predictionSchema.parse(value))
                  : options.evaluationModels!.generate(
                      modelId,
                      messages,
                      signal,
                    ),
            };
            const rows = await evaluatePairs({
              runId,
              generated: await json(artifact.key),
              dataset: await artifacts.read(dataset.evaluation.key),
              comparisonModelId: input.comparisonModelId,
              judgeModelId: input.judgeModelId,
              models,
              artifacts,
              signal: Context.current().cancellationSignal,
            });
            artifact = await putJson(
              `runs/${runId}/evaluation/predictions.json`,
              rows,
            );
          }
          await putJson(resultKey, artifact);
        }
        const predictions = predictionsSchema.parse(await json(artifact.key));
        const metrics = summarizePredictions(predictions);
        const placeholderCost = estimateOutputCost(
          predictions,
          input.baseModelId,
          input.comparisonModelId,
        );
        let pricing: EvaluationPricing | undefined;
        if (!placeholderCost && options.evaluationPricing) {
          const pricingKey = `runs/${runId}/evaluation/pricing.json`;
          try {
            if (await artifacts.exists(pricingKey)) {
              pricing = evaluationPricingSchema.parse(await json(pricingKey));
            } else {
              pricing = await options.evaluationPricing(
                input.baseModelId,
                input.comparisonModelId,
                Context.current().cancellationSignal,
              );
              await putJson(pricingKey, pricing);
            }
          } catch {
            Context.current().cancellationSignal.throwIfAborted();
          }
        }
        const priced = pricePredictions(
          predictions,
          pricing,
          placeholderCost !== null,
        );
        if (
          priced.some(
            (row) =>
              row.fine_tuned.cost_nano_usd !== undefined ||
              row.comparison.cost_nano_usd !== undefined,
          )
        ) {
          const pricedArtifact = await putJson(
            `runs/${runId}/evaluation/priced-predictions.json`,
            priced,
          );
          await putJson(resultKey, pricedArtifact);
        }
        const cost =
          placeholderCost ??
          (pricing ? estimateTokenCost(predictions, pricing) : null);
        const summary: RunEvaluation = {
          judging_method: metrics.judging_method,
          holdout_groups: metrics.holdout_groups,
          holdout_examples: metrics.holdout_examples,
          comparison_model_id: input.comparisonModelId,
          judge_model_id: input.judgeModelId,
          vs_comparison: {
            comparator_model_id: input.comparisonModelId,
            ...metrics.fractions,
          },
          cost_per_request_nano_usd: cost,
          ...(cost
            ? {
                cost_basis: placeholderCost
                  ? ("placeholder_output_only" as const)
                  : ("catalog_token_estimate" as const),
              }
            : {}),
          output_tokens_per_second: metrics.output_tokens_per_second,
          error_rate: 0,
        };
        await store.result(
          runId,
          "evaluation",
          summary,
          {
            type: "evaluation_completed",
            judge: input.judgeModelId,
            groups: metrics.holdout_groups,
            ...summary.vs_comparison,
          },
          Context.current().info.attempt,
        );
      }),
  };
};
export type TrainingExecutorActivities = ReturnType<
  typeof createTrainingExecutorActivities
>;
