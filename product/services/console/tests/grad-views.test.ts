import { describe, expect, it } from "vitest";

import {
  evalReportRows,
  formatMetric,
  selectionMetric,
} from "@/lib/grad/eval-report";
import {
  bestModel,
  deltaTone,
  formatDelta,
  formatInterval,
  passAtK,
} from "@/lib/grad/evals";
import {
  formatBytes,
  formatCost,
  formatDuration,
  shortId,
} from "@/lib/grad/format";
import {
  INTERRUPTION_LABEL,
  PHASE_LABEL,
  RUN_STATUS,
  canResumeRun,
  isTerminalRun,
} from "@/lib/grad/labels";
import { recordPreview, recordScores } from "@/lib/grad/records";
import {
  DEFAULT_MODEL,
  defaultModelFor,
  defaultRunForm,
  modelsForRecipe,
  runFormSchema,
  runRequest,
} from "@/lib/grad/run-form";
import type {
  EvalModelSummary,
  EvalReport,
  TrainableModel,
} from "@/lib/grad/types";
import {
  datasetNameFromFile,
  sha256Hex,
  uploadHeaders,
  uploadTarget,
} from "@/lib/grad/upload";
import { usageRange } from "@/lib/grad/usage";

const report = (patch: Partial<EvalReport>): EvalReport => ({
  metricName: "eval_loss",
  selectedStep: 400,
  bestStep: 400,
  finalStep: 600,
  trainRecords: 100,
  evalRecords: 10,
  warnings: [],
  ...patch,
});

describe("eval reports", () => {
  it("reads the recipe's selection metric and its direction", () => {
    expect(selectionMetric(report({ evalLoss: 0.41234 }))).toMatchObject({
      name: "Eval loss",
      mode: "min",
      value: 0.41234,
    });
    expect(
      selectionMetric(
        report({
          metricName: "preference_accuracy",
          metricMode: "max",
          preferenceAccuracy: 0.8,
        }),
      ),
    ).toMatchObject({ name: "Preference accuracy", mode: "max", value: 0.8 });
  });

  it("shows the fields each recipe writes and skips missing ones", () => {
    expect(
      evalReportRows(
        "dpo",
        report({
          preferenceAccuracy: 0.812,
          rewardMargin: 1.94,
          trainPairs: 3408,
        }),
      ),
    ).toEqual([
      { label: "Preference accuracy", value: "81.2%" },
      { label: "Reward margin", value: "1.94" },
      { label: "Train pairs", value: "3,408" },
    ]);
  });

  it("adds the router's quality and cost trade-off", () => {
    const rows = evalReportRows(
      "router",
      report({
        candidates: ["a", "b"],
        paretoSummary: {
          targetMaxDrop: 0.02,
          routedQuality: 0.8,
          qualityDrop: 0.012,
          qualityDropCi95: [0.004, 0.021],
          offloadRate: 0.64,
          costSavingsPct: 0.52,
          ece: 0.03,
          threshold: 0.7,
          temperature: 1,
        },
      }),
    );

    expect(rows).toEqual([
      { label: "Candidates", value: "a, b" },
      { label: "Offload rate", value: "64%" },
      { label: "Cost savings", value: "52%" },
      { label: "Quality drop", value: "1.2% (95% CI 0.4% to 2.1%)" },
    ]);
  });

  it("compares embeddings with the base encoder", () => {
    const rows = evalReportRows(
      "embedding",
      report({
        recallAt10: 0.91,
        baseline: {
          recallAt1: null,
          recallAt5: null,
          recallAt10: 0.79,
          mrr: null,
        },
      }),
    );

    expect(rows).toContainEqual({
      label: "Base model Recall@10",
      value: "79%",
    });
  });

  it("formats metrics with four significant digits", () => {
    expect(formatMetric(0.412345)).toBe("0.4123");
    expect(formatMetric(1.5)).toBe("1.5");
    expect(formatMetric(1234.56)).toBe("1,234.6");
  });
});

describe("eval summaries", () => {
  const summary = (model: string, overall: number): EvalModelSummary => ({
    model,
    overall,
    ciLow: overall - 0.02,
    ciHigh: overall + 0.02,
    passAtK: { "3": 0.9, "1": 0.7 },
    vsBaseline: null,
    tasks: 10,
    errors: 0,
    tokensPerTask: 100,
    costPer1kTasksUsd: null,
  });

  it("calls a difference only when its interval excludes zero", () => {
    expect(deltaTone({ delta: 0.05, ciLow: 0.02, ciHigh: 0.08 })).toBe(
      "success",
    );
    expect(deltaTone({ delta: -0.05, ciLow: -0.08, ciHigh: -0.01 })).toBe(
      "danger",
    );
    expect(deltaTone({ delta: 0.01, ciLow: -0.02, ciHigh: 0.04 })).toBe(
      "neutral",
    );
    expect(formatDelta(-0.0884)).toBe("−0.088");
    expect(formatInterval(-0.12, -0.057)).toBe("−0.120 to −0.057");
  });

  it("sorts pass@k and picks the best model", () => {
    expect(passAtK(summary("a", 0.5))).toEqual([
      { k: 1, value: 0.7 },
      { k: 3, value: 0.9 },
    ]);
    expect(bestModel([summary("a", 0.5), summary("b", 0.8)])?.model).toBe("b");
    expect(bestModel([])).toBeUndefined();
  });
});

describe("labels", () => {
  it("never mentions spot capacity", () => {
    const text = JSON.stringify([
      INTERRUPTION_LABEL,
      PHASE_LABEL,
      RUN_STATUS,
    ]).toLowerCase();

    expect(text).not.toContain("spot");
    expect(text).not.toContain("preempt");
  });

  it("resumes stopped, failed and cancelled runs only", () => {
    expect(canResumeRun("stopped_budget")).toBe(true);
    expect(canResumeRun("cancelled")).toBe(true);
    expect(canResumeRun("completed")).toBe(false);
    expect(canResumeRun("running")).toBe(false);
    expect(isTerminalRun("queued")).toBe(false);
  });
});

describe("formatting", () => {
  it("formats sizes, costs, durations and ids", () => {
    expect(formatBytes(167_772_160)).toBe("160 MB");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatCost(0.004)).toBe("<$0.01");
    expect(formatCost(50.8)).toBe("$50.80");
    expect(formatDuration(6900)).toBe("1 h 55 min");
    expect(formatDuration(20)).toBe("1 min");
    expect(shortId("run_01jdx3k8q2support")).toBe("run_01jdx3k8");
  });
});

describe("records", () => {
  it("previews chat transcripts", () => {
    expect(
      recordPreview({
        messages: [
          { role: "system", content: "Be brief." },
          {
            role: "user",
            content: [{ type: "text", text: "Reset my password" }],
          },
          { role: "assistant", content: "Open Settings." },
        ],
      }),
    ).toEqual({ input: "Reset my password", output: "Open Settings." });
  });

  it("previews prompt, preference and retrieval records", () => {
    expect(recordPreview({ prompt: "2+2?", completion: "4" })).toEqual({
      input: "2+2?",
      output: "4",
    });
    expect(
      recordPreview({ prompt: "Pick", chosen: "A", rejected: "B" }),
    ).toEqual({ input: "Pick", output: "A" });
    expect(
      recordPreview({ query: "refunds", positive: "Refund policy" }),
    ).toEqual({
      input: "refunds",
      output: "Refund policy",
    });
  });

  it("clips long text and lists scores", () => {
    expect(recordPreview({ prompt: "x".repeat(400) }).input).toHaveLength(280);
    expect(recordScores({ scores: { resolved: 1, csat: 4.25 } })).toEqual([
      "resolved 1",
      "csat 4.25",
    ]);
  });
});

describe("the new-run form", () => {
  const models: TrainableModel[] = [
    {
      id: "qwen3-8b",
      hfRepo: null,
      family: "llm",
      adapters: ["lora"],
      recipes: ["sft", "dpo"],
      defaultFor: ["sft"],
      pricePerMillionTokensUsd: 2,
      maxContextTokens: 32768,
      templateRevision: "r",
      calibratedLrs: {},
      minGpuMemoryGb: 38,
    },
    {
      id: "bge-base",
      hfRepo: null,
      family: "encoder",
      adapters: ["encoder_full"],
      recipes: ["embedding"],
      defaultFor: ["embedding"],
      pricePerMillionTokensUsd: 0.1,
      maxContextTokens: 512,
      templateRevision: "r",
      calibratedLrs: {},
      minGpuMemoryGb: 4,
    },
  ];

  it("offers the models that train a recipe", () => {
    expect(modelsForRecipe(models, "dpo").map((model) => model.id)).toEqual([
      "qwen3-8b",
    ]);
    expect(defaultModelFor(models, "embedding")).toBe("bge-base");
  });

  it("builds a plan request with only the fields the recipe uses", () => {
    expect(
      runRequest({
        ...defaultRunForm("support"),
        kind: "router",
        candidates: "qwen3-8b, gpt-4.1-mini",
        rubric: "resolved",
        teacher: "ignored",
        maxCostUsd: "25",
      }),
    ).toEqual({
      dataset: "support",
      name: "support-sft",
      recipe: {
        kind: "router",
        models: ["qwen3-8b", "gpt-4.1-mini"],
        rubric: "resolved",
      },
      maxCostUsd: 25,
    });
    expect(
      runRequest({
        ...defaultRunForm("support"),
        kind: "distill",
        model: "qwen3-8b",
        teacher: "qwen3-32b",
      }).recipe,
    ).toEqual({ kind: "distill", model: "qwen3-8b", teacher: "qwen3-32b" });
    expect(runRequest(defaultRunForm("support")).recipe).toEqual({
      kind: "sft",
    });
    expect(defaultRunForm().model).toBe(DEFAULT_MODEL);
  });

  it("validates names and the cost cap", () => {
    const parsed = runFormSchema.safeParse({
      ...defaultRunForm("support"),
      name: "Bad Name",
      maxCostUsd: "-1",
    });

    expect(parsed.success).toBe(false);
    expect(parsed.error?.issues.map((issue) => issue.path[0])).toEqual([
      "name",
      "maxCostUsd",
    ]);
  });
});

describe("uploads", () => {
  it("hashes the file the way grad's upload ticket expects", async () => {
    await expect(sha256Hex(new Blob(["abc"]))).resolves.toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });

  it("drops headers browsers set themselves and resolves relative URLs", () => {
    expect(
      uploadHeaders({ "Content-Length": "3", "x-amz-checksum-sha256": "abc" }),
    ).toEqual({
      "x-amz-checksum-sha256": "abc",
    });
    expect(uploadTarget("/v1/blobs/abc", "https://api.gradiated.com/")).toBe(
      "https://api.gradiated.com/v1/blobs/abc",
    );
    expect(
      uploadTarget(
        "https://bucket.s3.amazonaws.com/x?sig=1",
        "https://api.gradiated.com",
      ),
    ).toBe("https://bucket.s3.amazonaws.com/x?sig=1");
  });

  it("suggests a valid dataset name from the file name", () => {
    expect(datasetNameFromFile("Support Traces.jsonl.gz")).toBe(
      "support-traces",
    );
    expect(datasetNameFromFile("__export.parquet")).toBe("export");
  });
});

describe("usageRange", () => {
  const now = new Date("2026-11-27T15:30:00Z");

  it("covers this month or the last days, ending today", () => {
    expect(usageRange("month", now)).toEqual({
      from: "2026-11-01",
      to: "2026-11-27",
    });
    expect(usageRange("7d", now)).toEqual({
      from: "2026-11-21",
      to: "2026-11-27",
    });
    expect(usageRange("30d", now)).toEqual({
      from: "2026-10-29",
      to: "2026-11-27",
    });
  });
});
