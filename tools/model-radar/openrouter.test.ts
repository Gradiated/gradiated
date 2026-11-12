import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { OpenRouterSource } from "./openrouter.ts";
import { fakeFetch, json } from "./testing.ts";

const listing = (data: unknown) =>
  fakeFetch({ [OpenRouterSource.API]: json({ data }) });

describe("OpenRouterSource", () => {
  it("groups watched models by prefix and skips variants and aliases", async () => {
    const { send } = listing([
      {
        id: "moonshotai/kimi-k3.1-pro",
        name: "MoonshotAI: Kimi K3.1 Pro",
        context_length: 262144,
        hugging_face_id: "moonshotai/Kimi-K3.1-Pro",
      },
      { id: "moonshotai/kimi-k3.1-pro:free", name: "free tier" },
      { id: "~moonshotai/kimi-latest", name: "alias" },
      { id: "cohere/command-a-plus", name: "not watched" },
      { id: "Qwen/qwen3.8-27b", context_length: 1048576, hugging_face_id: "" },
    ]);

    const scans = await new OpenRouterSource(send, [
      "moonshotai",
      "qwen",
      "x-ai",
    ]).scan();

    assert.deepEqual(scans, [
      {
        scope: "openrouter:moonshotai",
        owner: "moonshotai",
        models: [
          {
            id: "moonshotai/kimi-k3.1-pro",
            owner: "moonshotai",
            name: "MoonshotAI: Kimi K3.1 Pro",
            url: "https://openrouter.ai/moonshotai/kimi-k3.1-pro",
            details: ["262k context", "weights: moonshotai/Kimi-K3.1-Pro"],
          },
        ],
      },
      {
        scope: "openrouter:qwen",
        owner: "qwen",
        models: [
          {
            id: "Qwen/qwen3.8-27b",
            owner: "qwen",
            name: "Qwen/qwen3.8-27b",
            url: "https://openrouter.ai/Qwen/qwen3.8-27b",
            details: ["1M context"],
          },
        ],
      },
      // A watched prefix with nothing listed yet still gets a scope, so its
      // first model alerts instead of being recorded silently.
      { scope: "openrouter:x-ai", owner: "x-ai", models: [] },
    ]);
  });

  it("fails the scan when the listing fails or has no model list", async () => {
    await assert.rejects(
      new OpenRouterSource(fakeFetch({}).send, ["qwen"]).scan(),
      /OpenRouter listing failed \(HTTP 404\)/,
    );
    const { send } = fakeFetch({
      [OpenRouterSource.API]: json({ error: "busy" }),
    });
    await assert.rejects(
      new OpenRouterSource(send, ["qwen"]).scan(),
      /had no model list/,
    );
  });
});
