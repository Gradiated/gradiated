import { createHash } from "node:crypto";

import Anthropic from "@anthropic-ai/sdk";
import { afterAll, beforeAll, describe, expect, inject, it } from "vitest";

import { useCases } from "./case.js";
import { chatMessages, chatSdk } from "./chat.js";
import { eventually } from "./eventually.js";
import {
  GatewayProcess,
  GENERATION_TIMEOUT_SECONDS,
} from "./gateway-process.js";
import { object, type JsonObject } from "./json.js";
import { freePort } from "./ports.js";

const { makeCase } = useCases();
const hash = (value: string): string =>
  createHash("sha256").update(value).digest("hex").slice(0, 16);
let gateway: GatewayProcess;

beforeAll(async () => {
  const stack = inject("stack");
  gateway = await GatewayProcess.start({
    ...stack,
    port: await freePort(),
    generationTimeoutSeconds: GENERATION_TIMEOUT_SECONDS,
    logName: "session-telemetry",
    logLevel: "info",
  });
});
afterAll(async () => {
  await gateway?.stop();
});

const terminalSpan = async (generation: string | null): Promise<JsonObject> => {
  expect(generation).toBeTruthy();
  let span: JsonObject | undefined;
  await eventually(
    async () => {
      for (const line of (await gateway.log()).split("\n").filter(Boolean)) {
        const event = object(JSON.parse(line));
        if (
          object(event.fields).event === "generation_terminal" &&
          object(event.fields).generation_id === generation
        ) {
          span = object(event.span);
          return true;
        }
      }
      return false;
    },
    5000,
    "terminal log with session telemetry",
  );
  return span!;
};

describe("session telemetry on the real gateway", () => {
  it("OpenAI defaults have no invented session; Responses cache keys are observable", async () => {
    const instance = await makeCase("vllm", { gatewayUrl: gateway.url });
    const client = chatSdk(instance);
    const first = await client.chat.completions
      .create({ model: instance.model, messages: chatMessages() })
      .withResponse();
    const defaults = await terminalSpan(
      first.response.headers.get("x-gradiated-generation-id"),
    );
    expect(defaults.effective_session_source).toBe("content_messages");
    expect(defaults.session_headers_present).toBe("");
    expect(defaults.effective_session_hash).toMatch(/^[0-9a-f]{16}$/);
    const second = await client.responses
      .create({
        model: instance.model,
        input: "Synthetic billing ticket",
        prompt_cache_key: "synthetic-openai-key",
      })
      .withResponse();
    const explicit = await terminalSpan(
      second.response.headers.get("x-gradiated-generation-id"),
    );
    expect(explicit.prompt_cache_key_hash).toBe(hash("synthetic-openai-key"));
    expect(explicit.effective_session_source).toBe("prompt_cache_key");
    expect(explicit.effective_session_hash).toBe(hash("synthetic-openai-key"));
  });

  it("Anthropic defaults and Claude Code metadata report the effective routing key", async () => {
    const instance = await makeCase("vllm", { gatewayUrl: gateway.url });
    const client = new Anthropic({
      apiKey: instance.key,
      baseURL: gateway.url,
      maxRetries: 0,
    });
    const first = await client.messages
      .create({
        model: instance.model,
        max_tokens: 16,
        messages: [{ role: "user", content: "Synthetic billing ticket" }],
      })
      .withResponse();
    const defaults = await terminalSpan(
      first.response.headers.get("x-gradiated-generation-id"),
    );
    expect(defaults.session_headers_present).toBe("");
    expect(defaults.effective_session_source).toBe("content_messages");
    const session = "synthetic-claude-session";
    const second = await client.messages
      .create(
        {
          model: instance.model,
          max_tokens: 16,
          metadata: {
            user_id: JSON.stringify({
              session_id: session,
              device_id: "must-not-log-device",
            }),
          },
          messages: [{ role: "user", content: "Synthetic billing ticket" }],
        },
        {
          headers: {
            "x-claude-code-session-id": session,
            "user-agent": "claude-cli/2.1.299 (external, sdk-cli)",
          },
        },
      )
      .withResponse();
    const span = await terminalSpan(
      second.response.headers.get("x-gradiated-generation-id"),
    );
    expect(span.client).toBe("claude-code");
    expect(span.claude_session_hash).toBe(hash(session));
    expect(span.anthropic_metadata_session_hash).toBe(hash(session));
    expect(span.effective_session_source).toBe("x-claude-code-session-id");
    expect(JSON.stringify(span)).not.toContain(session);
    expect(await gateway.log()).not.toContain("must-not-log-device");
  });

  it("captured OpenCode session headers stay stable across turns and drive routing", async () => {
    const instance = await makeCase("vllm", { gatewayUrl: gateway.url });
    const session = "synthetic-opencode-session";
    for (let turn = 0; turn < 2; turn++) {
      const response = await instance.http.post(instance.path, {
        headers: {
          ...instance.headers,
          "user-agent":
            "opencode/1.19.5 ai-sdk/provider-utils/4.0.23 runtime/bun/1.4.4",
          "x-opencode-session-id": session,
          "x-session-affinity": session,
          "x-session-id": session,
        },
        json: instance.body(),
      });
      expect(response.status).toBe(200);
      const span = await terminalSpan(
        response.headers["x-gradiated-generation-id"]!,
      );
      expect(span.client).toBe("opencode");
      for (const field of [
        "opencode_session_hash",
        "session_affinity_hash",
        "generic_session_hash",
      ])
        expect(span[field]).toBe(hash(session));
      expect(span.effective_session_source).toBe("x-opencode-session-id");
    }
  });

  it("captured Codex headers and body expose only session/thread identifiers", async () => {
    const instance = await makeCase("vllm", { gatewayUrl: gateway.url });
    const session = "synthetic-codex-session";
    const response = await instance.http.post("/v1/responses", {
      headers: {
        ...instance.headers,
        "user-agent":
          "codex_exec/0.166.0 (Debian 13.0.0; x86_64) unknown (codex_exec; 0.166.0)",
        "session-id": session,
        "thread-id": session,
        "x-client-request-id": session,
        "x-codex-window-id": `${session}:0`,
        "x-codex-turn-metadata": JSON.stringify({
          session_id: session,
          thread_id: session,
          workspaces: "must-not-log-workspaces",
        }),
      },
      json: {
        model: instance.model,
        input: "Synthetic billing ticket",
        prompt_cache_key: session,
        client_metadata: { session_id: session, thread_id: session },
      },
    });
    expect(response.status).toBe(200);
    const span = await terminalSpan(
      response.headers["x-gradiated-generation-id"]!,
    );
    for (const field of [
      "codex_session_hash",
      "codex_thread_hash",
      "codex_metadata_session_hash",
      "codex_metadata_thread_hash",
      "client_request_hash",
      "prompt_cache_key_hash",
      "client_metadata_session_hash",
      "client_metadata_thread_hash",
    ])
      expect(span[field]).toBe(hash(session));
    expect(span.client).toBe("codex");
    expect(span.codex_window_hash).toBe(hash(`${session}:0`));
    expect(span.effective_session_source).toBe("prompt_cache_key");
    expect(await gateway.log()).not.toContain("must-not-log-workspaces");
  });

  it("unrecognized conversation shapes log only the bounded content fallback hash", async () => {
    const instance = await makeCase("vllm", { gatewayUrl: gateway.url });
    const response = await instance.post({
      messages: [{ content: "private synthetic content" }],
    });
    expect(response.status).toBe(200);
    const span = await terminalSpan(
      response.headers["x-gradiated-generation-id"]!,
    );
    expect(span.effective_session_source).toBe("content_prefix_8192");
    expect(span.effective_session_hash).toMatch(/^[0-9a-f]{16}$/);
    expect(await gateway.log()).not.toContain("private synthetic content");
  });

  it("preserves SystemOne Unicode session bounds and hashes the accepted key", async () => {
    const instance = await makeCase("kev", {
      gatewayUrl: gateway.url,
      replicas: 2,
    });
    const session = "😀".repeat(128);
    for (let turn = 0; turn < 2; turn++) {
      const response = await instance.post({ session_id: session });
      expect(response.status).toBe(200);
      const span = await terminalSpan(
        response.headers["x-gradiated-generation-id"]!,
      );
      expect(span.effective_session_hash).toBe(hash(session));
      expect(span.body_session_hash).toBe(hash(session));
      expect(span.effective_session_source).toBe("body_session_id");
    }
    expect(
      instance.runtimes.filter((runtime) => runtime.calls.length > 0),
    ).toHaveLength(1);
    expect((await instance.post({ session_id: session + "x" })).status).toBe(
      400,
    );
    expect(await gateway.log()).not.toContain(session);
  });

  it("logs the actual routing session with body taking precedence over the header", async () => {
    const instance = await makeCase("vllm", { gatewayUrl: gateway.url });
    for (const body of [false, true]) {
      const response = await instance.http.post(instance.path, {
        headers: {
          ...instance.headers,
          "x-gradiated-session-id": "synthetic-header",
        },
        json: instance.body(body ? { session_id: "synthetic-body" } : {}),
      });
      expect(response.status).toBe(200);
      const span = await terminalSpan(
        response.headers["x-gradiated-generation-id"]!,
      );
      expect(span.effective_session_source).toBe(
        body ? "body_session_id" : "x-gradiated-session-id",
      );
      expect(span.effective_session_hash).toBe(
        hash(body ? "synthetic-body" : "synthetic-header"),
      );
      expect(span.session_id_hash).toBe(hash("synthetic-header"));
    }
  });
});
