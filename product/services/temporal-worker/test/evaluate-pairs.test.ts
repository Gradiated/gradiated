import { expect, it, vi } from "vitest";
import type { TrainingArtifacts } from "@gradiated/control";
import { evaluatePairs } from "../src/training/evaluate-pairs.js";

const prediction = { text: "fine", tokens: 1, seconds: 1 };
it("uses each task's comparison and judge once per pair and reuses completed pairs on retry", async () => {
  const saved = new Map<string, Uint8Array>();
  const generate = vi
    .fn()
    .mockResolvedValueOnce({ ...prediction, text: "comparison" })
    .mockResolvedValueOnce({ ...prediction, text: "A" });
  const input = {
    runId: "01900000-0000-7000-8000-000000000001",
    generated: [{ id: "one", group: "session", fine_tuned: prediction }],
    dataset: Buffer.from(
      JSON.stringify({
        id: "one",
        group: "session",
        prompt: [{ role: "user", content: "request" }],
      }),
    ),
    comparisonModelId: "openai/gpt-6.1-sol",
    judgeModelId: "anthropic/claude-sonnet-5-5",
    models: { check: vi.fn(), generate },
    signal: new AbortController().signal,
    artifacts: {
      exists: async (key: string) => saved.has(key),
      read: async (key: string) => saved.get(key)!,
      put: async (key: string, bytes: Uint8Array) => {
        saved.set(key, bytes);
        return { key, sha256: "a".repeat(64), size_bytes: bytes.length };
      },
    } as TrainingArtifacts,
  };
  const result = await evaluatePairs(input);
  expect(generate.mock.calls.map((call) => call[0])).toEqual([
    input.comparisonModelId,
    input.judgeModelId,
  ]);
  expect(JSON.parse(generate.mock.calls[1]![1][1].content)).toMatchObject({
    request: [{ role: "user", content: "request" }],
  });
  expect(await evaluatePairs(input)).toEqual(result);
  expect(generate).toHaveBeenCalledTimes(2);
});

it("rejects missing or duplicate GPU predictions before calling providers", async () => {
  const generate = vi.fn();
  await expect(
    evaluatePairs({
      runId: "test",
      generated: [{ id: "wrong", group: "session", fine_tuned: prediction }],
      dataset: Buffer.from(
        JSON.stringify({
          id: "one",
          group: "session",
          prompt: [{ role: "user", content: "request" }],
        }),
      ),
      comparisonModelId: "openai/gpt-6.1-sol",
      judgeModelId: "openai/gpt-6.1-sol",
      models: { check: vi.fn(), generate },
      artifacts: {} as TrainingArtifacts,
      signal: new AbortController().signal,
    }),
  ).rejects.toThrow("does not match");
  expect(generate).not.toHaveBeenCalled();
});
