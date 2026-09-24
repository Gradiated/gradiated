// A thread can move between a hosted model and a provider model from one turn
// to the next. These cases hold the direction the gateway controls: provider
// history arriving at our model, and our own history arriving back. The other
// direction needs the real providers; see test/live/thread-continuity.test.ts.
import { describe, expect, it } from "vitest";

import { useCases } from "../../../gateway/test/integration/case.js";
import {
  object,
  type JsonObject,
} from "../../../gateway/test/integration/json.js";
import { useProxy } from "./support/fixtures.js";
import {
  ANTHROPIC_TOOLS,
  CLAUDE_REDACTED,
  CLAUDE_SIGNATURE,
  claudeTurn,
  nextMessages,
  nextResponsesInput,
  OPENAI_ENCRYPTED,
  openAiTurn,
  OUR_REASONING,
  ourChatTurn,
  ourMessagesTurn,
  ourResponsesTurn,
  ourStreamedMessagesTurn,
  ourStreamedResponsesTurn,
  RESPONSES_TOOLS,
  STEPS,
  TOOL_OUTPUT,
} from "./support/threads.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

/** The chat request the gateway sent our runtime for the latest call. */
const runtimeRequest = (
  instance: Awaited<ReturnType<typeof fixture.hostedCase>>,
): JsonObject => instance.runtimes[0]!.calls.at(-1)!;

// Neither Anthropic nor OpenAI accepts reasoning it did not produce, so our
// reasoning reaches a client only in the one format both sides accept.
describe("what our model returns", () => {
  it.each(STEPS)(
    "returns a Messages %s with no thinking and no empty text",
    async (step) => {
      const instance = await fixture.hostedCase();

      const content = await ourMessagesTurn(
        fixture.proxy.client,
        instance,
        step,
      );

      expect(content.map((block) => object(block).type)).toEqual([
        step === "tool loop" ? "tool_use" : "text",
      ]);
      expect(JSON.stringify(content)).not.toContain(OUR_REASONING);
    },
  );

  it.each(STEPS)(
    "returns a Responses %s with no reasoning items",
    async (step) => {
      const instance = await fixture.hostedCase();

      const output = await ourResponsesTurn(
        fixture.proxy.client,
        instance,
        step,
      );

      expect(output.map((item) => object(item).type)).toEqual([
        step === "tool loop" ? "function_call" : "message",
      ]);
      expect(JSON.stringify(output)).not.toContain(OUR_REASONING);
    },
  );

  it.each(STEPS)(
    "streams a Messages %s with no thinking and no empty text",
    async (step) => {
      const instance = await fixture.hostedCase();

      const content = await ourStreamedMessagesTurn(
        fixture.proxy.url,
        instance,
        step,
      );

      expect(content.map((block) => object(block).type)).toEqual([
        step === "tool loop" ? "tool_use" : "text",
      ]);
      expect(JSON.stringify(content)).not.toContain(OUR_REASONING);
    },
  );

  it.each(STEPS)(
    "streams a Responses %s with no reasoning items",
    async (step) => {
      const instance = await fixture.hostedCase();

      const output = await ourStreamedResponsesTurn(
        fixture.proxy.url,
        instance,
        step,
      );

      expect(output.map((item) => object(item).type)).toEqual([
        step === "tool loop" ? "function_call" : "message",
      ]);
      expect(JSON.stringify(output)).not.toContain(OUR_REASONING);
    },
  );

  it.each(STEPS)(
    "keeps reasoning_content on a Chat Completions %s",
    async (step) => {
      const instance = await fixture.hostedCase();

      const message = await ourChatTurn(fixture.proxy.client, instance, step);

      expect(message.reasoning_content).toBe(OUR_REASONING);
    },
  );
});

describe("our own history coming back to our model", () => {
  it.each(STEPS)(
    "accepts a Messages %s that follows our reasoning",
    async (step) => {
      const instance = await fixture.hostedCase();
      const turn = await ourMessagesTurn(fixture.proxy.client, instance, step);

      const response = await fixture.proxy.client.post("/v1/messages", {
        headers: instance.headers,
        json: {
          model: instance.model,
          max_tokens: 64,
          tools: ANTHROPIC_TOOLS,
          messages: nextMessages(turn, step),
        },
      });

      expect(response.status, response.text).toBe(200);
      if (step === "tool loop")
        expect(JSON.stringify(runtimeRequest(instance))).toContain(TOOL_OUTPUT);
    },
  );

  it.each(STEPS)(
    "accepts a Responses %s that follows our reasoning",
    async (step) => {
      const instance = await fixture.hostedCase();
      const output = await ourResponsesTurn(
        fixture.proxy.client,
        instance,
        step,
      );

      const response = await fixture.proxy.client.post("/v1/responses", {
        headers: instance.headers,
        json: {
          model: instance.model,
          max_output_tokens: 64,
          store: false,
          tools: RESPONSES_TOOLS,
          input: nextResponsesInput(output, step),
        },
      });

      expect(response.status, response.text).toBe(200);
    },
  );
});

describe("provider history arriving at our model", () => {
  it.each(STEPS)(
    "serves a Messages %s after a Claude turn without sending Claude's encrypted reasoning to the runtime",
    async (step) => {
      const instance = await fixture.hostedCase();

      const response = await fixture.proxy.client.post("/v1/messages", {
        headers: instance.headers,
        json: {
          model: instance.model,
          max_tokens: 64,
          tools: ANTHROPIC_TOOLS,
          messages: nextMessages(claudeTurn(step), step),
        },
      });

      expect(response.status, response.text).toBe(200);
      const sent = JSON.stringify(runtimeRequest(instance));
      expect(sent).not.toContain(CLAUDE_SIGNATURE);
      expect(sent).not.toContain(CLAUDE_REDACTED);
      if (step === "tool loop") expect(sent).toContain(TOOL_OUTPUT);
    },
  );

  it.each(STEPS)(
    "serves a Codex-style Responses %s after an OpenAI turn without sending OpenAI's encrypted reasoning to the runtime",
    async (step) => {
      const instance = await fixture.hostedCase();

      const response = await fixture.proxy.client.post("/v1/responses", {
        headers: instance.headers,
        json: {
          model: instance.model,
          max_output_tokens: 64,
          store: false,
          include: ["reasoning.encrypted_content"],
          tools: RESPONSES_TOOLS,
          input: nextResponsesInput(openAiTurn(step), step),
        },
      });

      expect(response.status, response.text).toBe(200);
      const sent = JSON.stringify(runtimeRequest(instance));
      expect(sent).not.toContain(OPENAI_ENCRYPTED);
      if (step === "tool loop") expect(sent).toContain(TOOL_OUTPUT);
    },
  );
});
