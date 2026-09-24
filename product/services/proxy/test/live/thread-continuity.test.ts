// Real-provider thread continuity. A turn from our hosted model is replayed to
// Claude and to OpenAI through the proxy relay, in the forms a gateway change
// could produce, and real provider turns are replayed to our model. The
// results decide what the gateway returns as reasoning.
//
// Opt-in and paid. Each provider's cases run only when its key is set,
// the suite makes a fixed set of about twenty small calls, and it never runs in CI.
//
//   pnpm --filter @gradiated/proxy test:live   (keys from the root .env or .env.local)
import { describe, expect, it } from "vitest";

import { useCases, type Case } from "../../../gateway/test/integration/case.js";
import type { Response } from "../../../gateway/test/integration/http-client.js";
import {
  object,
  type JsonObject,
  type JsonValue,
} from "../../../gateway/test/integration/json.js";
import { useProxy } from "../e2e/support/fixtures.js";
import {
  ANTHROPIC_TOOLS,
  CHAT_TOOLS,
  nextChat,
  nextMessages,
  nextResponsesInput,
  ourChatTurn,
  ourMessagesTurn,
  ourResponsesTurn,
  PROMPT,
  RESPONSES_TOOLS,
  STEPS,
  type Step,
} from "../e2e/support/threads.js";

const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY;
const OPENAI_KEY = process.env.OPENAI_API_KEY;
const ANTHROPIC_MODEL = process.env.LIVE_ANTHROPIC_MODEL ?? "claude-sonnet-5";
const OPENAI_MODEL = process.env.LIVE_OPENAI_MODEL ?? "gpt-5.1";

const { makeCase } = useCases();
const fixture = useProxy(makeCase, {
  env: {
    PROXY_ANTHROPIC_ORIGIN: "https://api.anthropic.com",
    PROXY_OPENAI_ORIGIN: "https://api.openai.com",
    PROXY_PROVIDER_HEADER_SECONDS: "120",
    PROXY_IDLE_SECONDS: "120",
    PROXY_TOTAL_SECONDS: "180",
  },
});

const accepted = (response: Response): void => {
  expect(
    response.status,
    `provider answered ${response.status}: ${response.text}`,
  ).toBe(200);
};

const toClaude = (instance: Case, messages: JsonValue[]): Promise<Response> =>
  fixture.proxy.client.post("/v1/messages", {
    headers: {
      "x-api-key": ANTHROPIC_KEY!,
      "x-gradiated-api-key": instance.key,
      "anthropic-version": "2023-06-01",
    },
    json: {
      model: ANTHROPIC_MODEL,
      max_tokens: 2048,
      thinking: { type: "adaptive", display: "summarized" },
      tools: ANTHROPIC_TOOLS,
      messages,
    },
    timeoutMs: 120_000,
  });

const toOpenAi = (
  instance: Case,
  path: string,
  body: Record<string, unknown>,
): Promise<Response> =>
  fixture.proxy.client.post(path, {
    headers: {
      authorization: `Bearer ${OPENAI_KEY!}`,
      "x-gradiated-api-key": instance.key,
    },
    json: { model: OPENAI_MODEL, ...body },
    timeoutMs: 120_000,
  });

const toResponses = (instance: Case, input: JsonValue[]): Promise<Response> =>
  toOpenAi(instance, "/v1/responses", {
    store: false,
    include: ["reasoning.encrypted_content"],
    reasoning: { effort: "low" },
    max_output_tokens: 2048,
    tools: RESPONSES_TOOLS,
    input,
  });

describe.runIf(ANTHROPIC_KEY)(`our turn replayed to ${ANTHROPIC_MODEL}`, () => {
  describe.each(STEPS)("in a %s", (step: Step) => {
    it("accepts our turn as the gateway returns it", async () => {
      const instance = await fixture.hostedCase();
      const turn = await ourMessagesTurn(fixture.proxy.client, instance, step);

      accepted(await toClaude(instance, nextMessages(turn, step)));
    });
  });
});

describe.runIf(OPENAI_KEY)(`our turn replayed to ${OPENAI_MODEL}`, () => {
  describe.each(STEPS)("in a %s", (step: Step) => {
    it("accepts our Responses turn as the gateway returns it", async () => {
      const instance = await fixture.hostedCase();
      const output = await ourResponsesTurn(
        fixture.proxy.client,
        instance,
        step,
      );

      accepted(await toResponses(instance, nextResponsesInput(output, step)));
    });

    it("accepts our Chat Completions turn as the gateway returns it", async () => {
      const instance = await fixture.hostedCase();
      const message = await ourChatTurn(fixture.proxy.client, instance, step);

      accepted(
        await toOpenAi(instance, "/v1/chat/completions", {
          max_completion_tokens: 2048,
          tools: CHAT_TOOLS,
          messages: nextChat(message, step),
        }),
      );
    });
  });
});

describe("real provider turns replayed to our model", () => {
  it.runIf(ANTHROPIC_KEY)(
    `accepts a ${ANTHROPIC_MODEL} tool call with its thinking`,
    async () => {
      const instance = await fixture.hostedCase();
      const claude = await toClaude(instance, [
        { role: "user", content: PROMPT },
      ]);
      accepted(claude);
      const content = claude.json().content as JsonValue[];
      expect(content.map((block) => object(block).type)).toContain("tool_use");

      const response = await fixture.proxy.client.post("/v1/messages", {
        headers: instance.headers,
        json: {
          model: instance.model,
          max_tokens: 64,
          tools: ANTHROPIC_TOOLS,
          messages: nextMessages(content, "tool loop"),
        },
      });

      accepted(response);
      const signatures = content.flatMap((block) => {
        const { signature, data } = object(block);
        return [signature, data].filter(
          (value): value is string => typeof value === "string" && value !== "",
        );
      });
      const sent = JSON.stringify(instance.runtimes[0]!.calls.at(-1));
      for (const signature of signatures) expect(sent).not.toContain(signature);
    },
  );

  it.runIf(OPENAI_KEY)(
    `accepts a ${OPENAI_MODEL} tool call with its encrypted reasoning`,
    async () => {
      const instance = await fixture.hostedCase();
      const openai = await toResponses(instance, [
        { role: "user", content: PROMPT },
      ]);
      accepted(openai);
      const output = openai.json().output as JsonValue[];
      expect(output.map((item) => object(item).type)).toContain(
        "function_call",
      );

      const response = await fixture.proxy.client.post("/v1/responses", {
        headers: instance.headers,
        json: {
          model: instance.model,
          max_output_tokens: 64,
          store: false,
          tools: RESPONSES_TOOLS,
          input: nextResponsesInput(output, "tool loop"),
        },
      });

      accepted(response);
      const encrypted = output
        .map((item) => object(item).encrypted_content)
        .filter((value): value is string => typeof value === "string");
      const sent = JSON.stringify(instance.runtimes[0]!.calls.at(-1));
      for (const value of encrypted) expect(sent).not.toContain(value);
    },
  );
});
