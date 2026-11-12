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
            details: ["262k context"],
            weights: "moonshotai/Kimi-K3.1-Pro",
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

  describe("describe", () => {
    const API = OpenRouterSource.API;
    const HUB = OpenRouterSource.HUB_API;
    const hy4 = {
      id: "tencent/hy4",
      owner: "tencent",
      name: "Tencent: Hy4",
      url: "https://openrouter.ai/tencent/hy4",
      details: ["1M context"],
      weights: "tencent/Hy4",
    };
    const serving = (...names: string[]) =>
      json({
        data: { endpoints: names.map((provider_name) => ({ provider_name })) },
      });
    const details = async (
      routes: Record<string, () => Response>,
      model = hy4,
    ) => {
      const [described] = await new OpenRouterSource(
        fakeFetch(routes).send,
        [],
      ).describe([model]);
      return described!.details;
    };

    it("names the providers and says the weights are not public yet", async () => {
      assert.deepEqual(
        await details({
          [`${API}/tencent/hy4/endpoints`]: serving("Tencent"),
          [`${HUB}/tencent/Hy4`]: () =>
            new Response("private", { status: 401 }),
        }),
        ["1M context", "served by Tencent", "weights not public yet"],
      );
    });

    it("lists up to five providers, the lab's own first, once each", async () => {
      assert.deepEqual(
        await details({
          [`${API}/tencent/hy4/endpoints`]: serving(
            "Together",
            "Fireworks",
            "Tencent",
            "Fireworks",
          ),
          [`${HUB}/tencent/Hy4`]: json({ id: "tencent/Hy4" }),
        }),
        [
          "1M context",
          "served by Tencent, Together and Fireworks",
          "weights live",
        ],
      );
    });

    it("counts the providers when there are more than five", async () => {
      const kimi = {
        ...hy4,
        id: "moonshotai/kimi-k3.1-pro",
        name: "MoonshotAI: Kimi K3.1 Pro",
      };
      delete (kimi as { weights?: string }).weights;
      assert.deepEqual(
        await details(
          {
            [`${API}/moonshotai/kimi-k3.1-pro/endpoints`]: serving(
              "Together",
              "Fireworks",
              "DeepInfra",
              "Nebius",
              "Parasail",
              "Moonshot AI",
            ),
          },
          kimi,
        ),
        ["1M context", "served by Moonshot AI and 5 others"],
      );
    });

    it("leaves out what it could not look up", async () => {
      assert.deepEqual(
        await details({
          [`${HUB}/tencent/Hy4`]: () => new Response("busy", { status: 503 }),
        }),
        ["1M context"],
      );
    });
  });
});
