import { randomUUID } from "node:crypto";
import * as zlib from "node:zlib";
import { v7 as uuidv7 } from "uuid";
import { SftExampleSchema } from "@gradiated/contracts";
import { expect, it } from "vitest";
import { buildSftDataset, type SftExample } from "../src/training/dataset.js";
import { createMemoryContentStore } from "./support/content-store.js";

const compress = (
  zlib as unknown as { zstdCompressSync: (bytes: Uint8Array) => Buffer }
).zstdCompressSync;

type Sample = {
  prompt: string;
  answer: string;
  traceId: string;
  tools?: boolean;
  relay?: boolean;
  untrainable?: boolean;
  truncated?: boolean;
};

const ordinarySamples = (): Sample[] =>
  Array.from({ length: 200 }, (_, index) => ({
    prompt: `question-${Math.floor(index / 2)}`,
    answer: `answer-${index}`,
    traceId: `trace-${index}`,
  }));

const createDatasetInput = (samples: Sample[]) => {
  const workspaceId = randomUUID();
  const objects = new Map<string, Buffer>();
  const now = new Date();
  const key = `v1/ws=${workspaceId}/task=test/dt=${now.toISOString().slice(0, 10)}/hr=${now.toISOString().slice(11, 13)}/batch.manifest.json`;
  const frames: Buffer[] = [];
  let offset = 0;
  const rows = samples.map((sample) => {
    const generation_id = uuidv7();
    const canonical = {
      version: 1,
      messages: [
        {
          role: "user",
          content: sample.prompt,
        },
      ],
      tools: sample.tools ? [{ type: "function" }] : [],
      output: {
        role: "assistant",
        content: sample.answer,
      },
    };
    const frame = compress(
      Buffer.from(
        JSON.stringify({
          generation_id,
          workspace_id: workspaceId,
          canonical,
        }),
      ),
    );
    frames.push(frame);
    const row = {
      generation_id,
      workspace_id: workspaceId,
      task: "test",
      trace_id: sample.traceId,
      model: "Qwen/Qwen3-0.6B",
      source: sample.relay ? "relay" : "hosted",
      trainable: !sample.untrainable,
      started_at: now.toISOString(),
      completed_at: now.toISOString(),
      status: 200,
      outcome: sample.truncated ? "truncated" : "complete",
      usage: null,
      retention_days: 30,
      offset,
      length: frame.length,
    };
    offset += frame.length;
    return row;
  });
  objects.set(
    key,
    Buffer.from(
      JSON.stringify({
        schema: "gradiated.generation-content-manifest/1",
        generations: rows,
      }),
    ),
  );
  objects.set(
    key.replace(".manifest.json", ".jsonl.zst"),
    Buffer.concat(frames),
  );
  const store = createMemoryContentStore(objects, now.toISOString());
  const input = {
    taskId: randomUUID(),
    workspaceId,
    name: "test",
    baseModelId: "Qwen/Qwen3-0.6B",
    comparisonModelId: "Qwen/Qwen3-0.6B",
    judgeModelId: "Qwen/Qwen3-0.6B" as const,
    inputCutoff: new Date(Date.now() + 1).toISOString(),
    trigger: "manual" as const,
    requestedBy: randomUUID(),
  };
  return { store, input };
};

it.each(["relay", "untrainable", "tools", "truncated", "duplicate"])(
  "excludes %s examples and keeps related prompts in one split",
  async (excluded) => {
    const samples = ordinarySamples();
    samples.push({
      prompt: excluded === "duplicate" ? samples[0]!.prompt : "question-100",
      answer: excluded === "duplicate" ? samples[0]!.answer : "answer-200",
      traceId: "trace-200",
      tools: excluded === "tools",
      relay: excluded === "relay",
      untrainable: excluded === "untrainable",
      truncated: excluded === "truncated",
    });
    const { store, input } = createDatasetInput(samples);
    const result = await buildSftDataset(store, input);
    expect(result.summary.eligible_examples).toBe(
      excluded === "duplicate" ? 201 : 200,
    );
    expect(result.summary.duplicates_removed).toBe(
      excluded === "duplicate" ? 1 : 0,
    );
    expect(
      result.summary.train + result.summary.validation + result.summary.test,
    ).toBe(200);
    const seen = new Map<string, string>();
    for (const [split, bytes] of Object.entries(result.files)) {
      const examples: SftExample[] = bytes
        .toString()
        .trim()
        .split("\n")
        .map((line) => JSON.parse(line));
      expect(examples.length).toBeGreaterThan(0);
      for (const example of examples) {
        expect(SftExampleSchema.safeParse(example).success).toBe(true);
        expect(example).not.toHaveProperty("target");
        expect(example).not.toHaveProperty("messages");
        const prompt = JSON.stringify(example.prompt);
        if (seen.has(prompt)) expect(seen.get(prompt)).toBe(split);
        seen.set(prompt, split);
        expect(example.completion[0]!.content).not.toBe("answer-200");
      }
    }
    expect(await buildSftDataset(store, input)).toEqual(result);
  },
);

it("keeps transitive session, duplicate and shared-prompt relationships in one split", async () => {
  const samples = ordinarySamples();
  samples.push(
    { traceId: "session-a", prompt: "bridge-1", answer: "answer-a1" },
    { traceId: "session-a", prompt: "bridge-2", answer: "answer-a2" },
    { traceId: "session-b", prompt: "bridge-2", answer: "answer-a2" },
    { traceId: "session-b", prompt: "bridge-3", answer: "answer-b" },
    { traceId: "session-c", prompt: "bridge-3", answer: "answer-c" },
  );
  const { store, input } = createDatasetInput(samples);
  const result = await buildSftDataset(store, input);
  const related: Array<{ split: string; example: SftExample }> = [];
  for (const [split, bytes] of Object.entries(result.files)) {
    for (const line of bytes.toString().trim().split("\n")) {
      const example = SftExampleSchema.parse(JSON.parse(line)) as SftExample;
      if (example.prompt[0]!.content.startsWith("bridge-"))
        related.push({ split, example });
    }
  }
  expect(related).toHaveLength(4);
  expect(new Set(related.map(({ split }) => split)).size).toBe(1);
  expect(new Set(related.map(({ example }) => example.group))).toEqual(
    new Set(["session-a"]),
  );
  expect(result.summary).toMatchObject({
    eligible_examples: 205,
    duplicates_removed: 1,
  });
});
