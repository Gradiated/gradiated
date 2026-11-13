import { describe, expect, it } from "vitest";

import { serverSentEventData } from "@/api/inference";
import type { Model } from "@/api/queries";
import {
  chatRequest,
  DEFAULT_SETTINGS,
  effectiveSettings,
  NO_CAPABILITIES,
  playgroundModels,
  replyStats,
  reasoningEfforts,
  requestSnippet,
  type ModelCapabilities,
  type ModelParameters,
  type PlaygroundMessage,
  type PlaygroundSettings,
} from "@/lib/playground";
import type { TaskRow } from "@/store/fine-tuning-types";

const hosted = (
  id: string,
  patch: {
    status?: Model["status"];
    type?: "chat" | "decision";
    parameters?: ModelParameters;
    defaults?: Model["properties"]["default_parameters"];
    reasoning?: Model["properties"]["reasoning"];
  } = {},
) =>
  ({
    id,
    name: id,
    status: patch.status ?? "available",
    properties: {
      type: patch.type ?? "chat",
      output_modalities: [
        {
          type: "text",
          default_length: { value: 4096, unit: "token" },
          max_length: { value: 131072, unit: "token" },
          supported_parameters: patch.parameters ?? {},
        },
      ],
      default_parameters: patch.defaults,
      reasoning: patch.reasoning,
    },
  }) as unknown as Model;

const task = (name: string, production: boolean): TaskRow => ({
  id: `${name}-id`,
  name,
  base_model_id: "z-ai/glm-5.3-flash",
  comparison_model_id: null,
  production_version_id: production ? `${name}-version` : null,
  judge_model_id: "Qwen/Qwen3-0.6B",
  training_schedule: null,
});

const settings: PlaygroundSettings = {
  ...DEFAULT_SETTINGS,
  model: "z-ai/glm-5.3-flash",
  capabilities: NO_CAPABILITIES,
};

const withCapabilities = (
  capabilities: Partial<ModelCapabilities>,
  patch: Partial<PlaygroundSettings> = {},
): PlaygroundSettings => ({
  ...settings,
  ...patch,
  capabilities: { ...NO_CAPABILITIES, ...capabilities },
});

const glm: Partial<ModelCapabilities> = {
  parameters: {
    temperature: { type: "range", min: 0, max: 2 },
    top_p: { type: "range", min: 0, max: 1 },
    reasoning_effort: { type: "enum", values: ["low", "high", "max"] },
  },
  outputTokens: { default: 4096, max: 131072 },
  defaults: { temperature: 1, top_p: 0.95 },
  reasoning: {
    supported_efforts: ["low", "high", "max"],
    default_effort: "max",
  },
};

const conversation: PlaygroundMessage[] = [
  { id: "1", role: "user", content: "Hi" },
  {
    id: "2",
    role: "assistant",
    content: "Hello!",
    reasoning: "Greet back.",
    status: "complete",
  },
  { id: "3", role: "user", content: "Retry this" },
  {
    id: "4",
    role: "assistant",
    content: "",
    reasoning: "",
    status: "failed",
    error: "Rejected",
  },
  { id: "5", role: "user", content: "Again" },
  {
    id: "6",
    role: "assistant",
    content: "",
    reasoning: "Started thinking",
    status: "stopped",
  },
];

describe("playgroundModels", () => {
  it("ignores report task context belonging to a different selected model", () => {
    const models = playgroundModels(
      [],
      [task("support-assistant", true), task("billing", true)],
      "acme",
      { task: "support-assistant", name: "acme/billing" },
    );

    expect(models.map(({ id }) => id)).toEqual([
      "acme/support-assistant",
      "acme/billing",
    ]);
  });
  it("keeps the exact version from a report link alongside the production task", () => {
    const models = playgroundModels(
      [hosted("z-ai/glm-5.3-flash")],
      [task("support-assistant", true)],
      "acme",
      { task: "support-assistant", name: "acme/support-assistant/v2" },
    );

    expect(models.map(({ id }) => id)).toEqual([
      "z-ai/glm-5.3-flash",
      "acme/support-assistant",
      "acme/support-assistant/v2",
    ]);
    expect(models[2]?.capabilities).toEqual(models[1]?.capabilities);
  });
  it("lists hosted chat models, then tasks with a production version", () => {
    const models = playgroundModels(
      [
        hosted("z-ai/glm-5.3-flash"),
        hosted("deepseek/deepseek-v4.1-flash-1017", { status: "unavailable" }),
        hosted("jaredpalmer/kev-9b", { type: "decision" }),
        hosted("Qwen/Qwen3-8B"),
      ],
      [task("support-assistant", true), task("untrained", false)],
      "acme",
    );

    expect(
      models.map(({ id, source, available }) => [id, source, available]),
    ).toEqual([
      ["z-ai/glm-5.3-flash", "hosted", true],
      ["deepseek/deepseek-v4.1-flash-1017", "hosted", false],
      ["acme/support-assistant", "workspace", true],
    ]);
    expect(models[0]?.label).toBe("GLM-5.3 Flash");
    expect(models[2]?.label).toBe("acme/support-assistant");
    expect(models[2]?.iconId).toBe("z-ai/glm-5.3-flash");
  });

  it("leaves out a task whose name is also a hosted model id", () => {
    const models = playgroundModels(
      [hosted("z-ai/glm-5.3-flash")],
      [task("glm-5.3-flash", true), task("support-assistant", true)],
      "z-ai",
    );

    expect(models.map(({ id, source }) => [id, source])).toEqual([
      ["z-ai/glm-5.3-flash", "hosted"],
      ["z-ai/support-assistant", "workspace"],
    ]);
  });

  it("reads capabilities from the catalog and gives a task its base model's", () => {
    const parameters: ModelParameters = {
      temperature: { type: "range", min: 0, max: 2 },
    };
    const [model, task_] = playgroundModels(
      [
        hosted("z-ai/glm-5.3-flash", {
          parameters,
          defaults: { temperature: 1 },
        }),
      ],
      [task("support-assistant", true)],
      "acme",
    );

    expect(task_?.capabilities).toEqual(model?.capabilities);
    expect(task_?.capabilities).toEqual({
      parameters,
      outputTokens: { default: 4096, max: 131072 },
      defaults: { temperature: 1 },
      reasoning: undefined,
    });
  });
});

describe("reasoningEfforts", () => {
  it("lists the catalog's efforts, else the enum values, else none", () => {
    expect(reasoningEfforts({ ...NO_CAPABILITIES, ...glm })).toEqual([
      "low",
      "high",
      "max",
    ]);
    expect(
      reasoningEfforts({
        ...NO_CAPABILITIES,
        parameters: {
          reasoning_effort: { type: "enum", values: ["low", "high"] },
        },
      }),
    ).toEqual(["low", "high"]);
    expect(
      reasoningEfforts({
        ...NO_CAPABILITIES,
        parameters: { reasoning_effort: { type: "unknown" } },
      }),
    ).toEqual([]);
  });
});

describe("chatRequest", () => {
  it("sends history without failed or empty replies or reasoning", () => {
    expect(chatRequest(settings, conversation)).toEqual({
      model: "z-ai/glm-5.3-flash",
      messages: [
        { role: "user", content: "Hi" },
        { role: "assistant", content: "Hello!" },
        { role: "user", content: "Retry this" },
        { role: "user", content: "Again" },
      ],
      service_tier: "default",
    });
  });

  it("adds the system prompt and sends the catalog defaults it shows", () => {
    const request = chatRequest(
      withCapabilities(glm, { systemPrompt: "  Be brief.  ", temperature: 0 }),
      conversation.slice(0, 1),
    );

    expect(request).toEqual({
      model: "z-ai/glm-5.3-flash",
      messages: [
        { role: "system", content: "Be brief." },
        { role: "user", content: "Hi" },
      ],
      service_tier: "default",
      reasoning_effort: "max",
      temperature: 0,
      top_p: 0.95,
      max_completion_tokens: 4096,
    });
  });

  it("returns to the default effort when the model lacks the chosen one", () => {
    expect(
      effectiveSettings(withCapabilities(glm, { reasoningEffort: "medium" }))
        .reasoningEffort,
    ).toBe("max");
  });

  it("leaves values the catalog does not publish unset", () => {
    expect(
      effectiveSettings(
        withCapabilities({
          parameters: { temperature: { type: "range", min: 0, max: 2 } },
        }),
      ),
    ).toEqual({
      temperature: undefined,
      topP: undefined,
      frequencyPenalty: undefined,
      presencePenalty: undefined,
      maxTokens: undefined,
      reasoningEffort: undefined,
    });
  });

  it("sends the service tier and the optional parameters the model accepts", () => {
    const request = chatRequest(
      withCapabilities(
        {
          parameters: {
            reasoning_effort: { type: "unknown" },
            stop: { type: "unknown" },
            response_format: { type: "unknown" },
          },
          reasoning: {
            supported_efforts: ["low", "high"],
            default_effort: null,
          },
        },
        {
          serviceTier: "fast",
          reasoningEffort: "high",
          seed: 7,
          stop: "END\n\n###",
          jsonOutput: true,
        },
      ),
      conversation.slice(0, 1),
    );

    expect(request).toEqual({
      model: "z-ai/glm-5.3-flash",
      messages: [{ role: "user", content: "Hi" }],
      service_tier: "fast",
      reasoning_effort: "high",
      stop: ["END", "###"],
      response_format: { type: "json_object" },
    });
  });

  it("drops optional parameters the selected model does not accept", () => {
    expect(
      chatRequest(
        { ...settings, reasoningEffort: "high", seed: 7, stop: "END" },
        conversation.slice(0, 1),
      ),
    ).toEqual({
      model: "z-ai/glm-5.3-flash",
      messages: [{ role: "user", content: "Hi" }],
      service_tier: "default",
    });
  });
});

describe("replyStats", () => {
  const usage = {
    cost: 0.00042,
    prompt_tokens: 12,
    completion_tokens: 50,
    total_tokens: 62,
    prompt_tokens_details: { cached_tokens: 0 },
    completion_tokens_details: { reasoning_tokens: 0 },
  };

  it("measures throughput after the first token", () => {
    expect(replyStats({ firstTokenMs: 200, totalMs: 1200, usage })).toEqual([
      "50 tokens",
      "50 tok/s",
      "200 ms to first token",
      "$0.000420",
    ]);
  });

  it("omits what the stream did not report", () => {
    expect(
      replyStats({ firstTokenMs: undefined, totalMs: 0, usage: undefined }),
    ).toEqual([]);
  });
});

describe("requestSnippet", () => {
  const request = chatRequest(
    withCapabilities(
      { parameters: { temperature: { type: "range", min: 0, max: 2 } } },
      { temperature: 0.2 },
    ),
    [{ id: "1", role: "user", content: "It's fine" }],
  );

  it("escapes single quotes in the cURL body", () => {
    expect(requestSnippet("curl", request)).toContain(`"It'\\''s fine"`);
  });

  it("passes parameters as SDK keyword arguments", () => {
    const python = requestSnippet("python", request);

    expect(python).toContain('model="z-ai/glm-5.3-flash"');
    expect(python).toContain("    temperature=0.2,\n)");
  });
});

describe("serverSentEventData", () => {
  const collect = async (chunks: string[]) => {
    const events = new ReadableStream<string>({
      start: (controller) => {
        for (const chunk of chunks) controller.enqueue(chunk);
        controller.close();
      },
    }).pipeThrough(serverSentEventData());
    const reader = events.getReader();
    const data: string[] = [];

    for (;;) {
      const { value, done } = await reader.read();
      if (done) return data;

      data.push(value);
    }
  };

  it("joins events split across chunks and ignores comments", async () => {
    expect(
      await collect([
        ': keep-alive\n\ndata: {"a"',
        ":1}\r\n\r\ndata: line one\ndata: line two\n\n",
        "data: [DONE]",
      ]),
    ).toEqual(['{"a":1}', "line one\nline two", "[DONE]"]);
  });
});
