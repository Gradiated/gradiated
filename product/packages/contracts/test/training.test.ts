import { describe, expect, it } from "vitest";
import {
  MODEL_CATALOG,
  EVALUATION_JUDGES,
  DEFAULT_EVALUATION_JUDGE,
} from "../src/model-catalog.js";
import { UpdateWorkspaceSchema } from "../src/workspaces.js";
import {
  EvaluationJudgeSchema,
  UpdateTaskSchema,
  TrainingRunEventSchema,
  TrainerEventPayloadSchema,
} from "../src/training.js";

describe("event service sources", () => {
  const event = {
    id: 1,
    at: "2026-09-29T12:00:00.000Z",
    attempt: 1,
    payload: { type: "note", level: "info", message: "test" },
  };

  it.each(["api", "worker", "trainer", "adapter-publisher"])(
    "accepts service %s without extending an enum",
    (source) => {
      expect(TrainingRunEventSchema.parse({ ...event, source }).source).toBe(
        source,
      );
    },
  );

  it.each(["", "arbitrary text", "a".repeat(65)])(
    "rejects an invalid service name",
    (source) => {
      expect(
        TrainingRunEventSchema.safeParse({ ...event, source }).success,
      ).toBe(false);
    },
  );
});

describe("shared model catalog", () => {
  it("derives judge validation and options from supported uses", () => {
    const judgeIds = MODEL_CATALOG.filter((model) =>
      (model.supportedUses as readonly string[]).includes("judge"),
    ).map((model) => model.id);
    expect(EVALUATION_JUDGES).toEqual(judgeIds);
    expect(new Set(MODEL_CATALOG.map((model) => model.id)).size).toBe(
      MODEL_CATALOG.length,
    );
    for (const id of judgeIds) {
      expect(EvaluationJudgeSchema.parse(id)).toBe(id);
      expect(
        UpdateWorkspaceSchema.parse({ default_judge_model: id })
          .default_judge_model,
      ).toBe(id);
    }
    expect(
      EvaluationJudgeSchema.safeParse(DEFAULT_EVALUATION_JUDGE).success,
    ).toBe(true);
    expect(
      UpdateWorkspaceSchema.safeParse({ default_judge_model: "unknown/model" })
        .success,
    ).toBe(false);
  });
});

describe("training measurements", () => {
  const envelope = {
    id: 1,
    at: "2026-09-29T12:00:00.000Z",
    source: "trainer",
    attempt: 1,
  };

  it("accepts sparse progress without inventing loss, totals or reward", () => {
    expect(
      TrainingRunEventSchema.parse({
        ...envelope,
        payload: { type: "trainer_progress", step: 0 },
      }).payload,
    ).toEqual({ type: "trainer_progress", step: 0 });
  });

  it("preserves method-specific metrics and signed objective losses", () => {
    const payload = {
      type: "trainer_progress",
      step: 20,
      train_loss: -0.1,
      metrics: {
        learning_rate: 0.0002,
        grad_norm: 1.2,
        "reward/mean": -2,
        "custom/loss_component": 0.3,
      },
    };
    expect(
      TrainingRunEventSchema.parse({ ...envelope, payload }).payload,
    ).toEqual(payload);
  });

  it("records validation independently of training progress", () => {
    const payload = {
      type: "trainer_observation",
      step: 20,
      name: "validation_completed",
      message: "Validation completed",
      metrics: { validation_loss: 0.8, accuracy: 0.7 },
    };
    expect(
      TrainingRunEventSchema.parse({ ...envelope, payload }).payload,
    ).toEqual(payload);
  });

  it.each([NaN, Infinity, "1.0", null, { nested: 1 }])(
    "rejects a non-finite or non-numeric metric %s",
    (value) => {
      expect(
        TrainingRunEventSchema.safeParse({
          ...envelope,
          payload: {
            type: "trainer_progress",
            step: 1,
            metrics: { custom: value },
          },
        }).success,
      ).toBe(false);
    },
  );

  it("bounds metric payloads without enumerating their names", () => {
    const metrics = Object.fromEntries(
      Array.from({ length: 65 }, (_, i) => [`metric_${i}`, i]),
    );
    expect(
      TrainingRunEventSchema.safeParse({
        ...envelope,
        payload: { type: "trainer_progress", step: 1, metrics },
      }).success,
    ).toBe(false);
  });
});

describe("trainer observations and workflow events", () => {
  const envelope = {
    id: 1,
    at: "2026-09-29T12:00:00.000Z",
    source: "trainer",
    attempt: 1,
  };

  it("preserves new observation names and structured details without a schema update", () => {
    const payload = {
      type: "trainer_observation",
      name: "teacher_batch_scored",
      message: "Teacher scored the batch",
      level: "debug",
      step: 10,
      metrics: { agreement: 0.8 },
      details: { teacher: { revision: "v2" }, batch_ids: [1, 2], cached: true },
    };
    expect(
      TrainingRunEventSchema.parse({ ...envelope, payload }).payload,
    ).toEqual(payload);
  });

  it("requires checkpoint identity for recovery", () => {
    expect(
      TrainingRunEventSchema.safeParse({
        ...envelope,
        payload: {
          type: "trainer_checkpoint",
          step: 10,
          sha256: "a".repeat(64),
        },
      }).success,
    ).toBe(false);
    const payload = {
      type: "trainer_checkpoint",
      step: 10,
      key: "runs/example/checkpoint.tar.gz",
      sha256: "a".repeat(64),
      size_bytes: 1024,
    };
    expect(
      TrainingRunEventSchema.parse({ ...envelope, payload }).payload,
    ).toEqual(payload);
  });

  it("keeps lifecycle types and states closed", () => {
    for (const payload of [
      { type: "unknown_transition" },
      { type: "stage_entered", stage: "arbitrary" },
    ]) {
      expect(
        TrainingRunEventSchema.safeParse({ ...envelope, payload }).success,
      ).toBe(false);
    }
  });
});

it("accepts trainer observations but rejects trainer lifecycle commands", () => {
  expect(
    TrainerEventPayloadSchema.safeParse({
      type: "trainer_observation",
      name: "finished",
      message: "Trainer finished",
    }).success,
  ).toBe(true);
  for (const payload of [
    { type: "stage_entered", stage: "succeeded" },
    { type: "run_finished", stage: "succeeded" },
    {
      type: "published",
      version_id: "00000000-0000-4000-8000-000000000000",
      name: "adapter",
    },
  ])
    expect(TrainerEventPayloadSchema.safeParse(payload).success).toBe(false);
});

it("rejects URL dot-segment task names while accepting long captured labels", async () => {
  const { TaskNameSchema } = await import("../src/training.js");
  for (const name of [".", ".."])
    expect(TaskNameSchema.safeParse(name).success).toBe(false);
  for (const name of ["Billing Questions", "a".repeat(256), "a.b"])
    expect(TaskNameSchema.parse(name)).toBe(name);
});

describe("task training cron", () => {
  it.each([
    "0 3 * * MON",
    "*/15 9-17 * * MON-FRI",
    "0 0 1 JAN,APR,JUL,OCT *",
    null,
  ])("accepts schedule %s", (training_schedule) => {
    expect(UpdateTaskSchema.parse({ training_schedule })).toEqual({
      training_schedule,
    });
  });

  it.each([
    "",
    "not a cron",
    "60 3 * * MON",
    "0 24 * * *",
    "0 0 32 * *",
    "0 0 * 13 *",
    "0 0 * * 8",
    "0 0 0 * * *",
    "0 0 L * *",
    "0 0 * * MON#2",
  ])("rejects invalid or unsupported schedule %s", (training_schedule) => {
    expect(UpdateTaskSchema.safeParse({ training_schedule }).success).toBe(
      false,
    );
  });
});

it.each([
  "openai/gpt-4.1-mini",
  "anthropic/claude-haiku-4-5",
  "z-ai/glm-5.3-flash",
])("allows %s for both comparison and judge", (id) => {
  expect(
    UpdateTaskSchema.parse({ comparison_model_id: id, judge_model_id: id }),
  ).toMatchObject({ comparison_model_id: id, judge_model_id: id });
  expect(
    UpdateWorkspaceSchema.parse({ default_judge_model: id })
      .default_judge_model,
  ).toBe(id);
});
