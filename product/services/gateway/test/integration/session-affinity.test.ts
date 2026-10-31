import { describe, expect, it } from "vitest";

import { useCases } from "./case.js";
import { expectRejected } from "./assertions.js";
import type { JsonObject } from "./json.js";

const { makeCase } = useCases();
const SOURCES = [
  "prompt_cache_key",
  "x-claude-code-session-id",
  "x-opencode-session-id",
  "x-session-affinity",
  "session-id",
  "thread-id",
  "x-session-id",
  "client_metadata",
  "x-codex-turn-metadata",
  "anthropic_metadata",
] as const;

describe("SDK cache affinity across wire formats and runtime releases", () => {
  it.each(SOURCES)(
    "%s selects the same replica and release as an explicit session",
    async (source) => {
      const instance = await makeCase("vllm", { replicas: 4 });
      for (const deployment of instance.deployments.slice(2))
        deployment.release = {
          ...instance.release,
          runtime_revision: "next-runtime",
        };
      await instance.publish();
      await instance.status();
      for (let index = 0; index < 6; index++) {
        const session = `${source}-${index}`;
        const before = instance.runtimes.map((runtime) => runtime.calls.length);
        expect((await instance.post({ session_id: session })).status).toBe(200);
        const selected = instance.runtimes.findIndex(
          (runtime, index) => runtime.calls.length > before[index]!,
        );
        const headers: Record<string, string> = { ...instance.headers };
        let path = instance.path;
        let body: JsonObject = instance.body({
          messages: [{ role: "user", content: `Different prompt ${index}` }],
        });
        if (source === "prompt_cache_key") {
          path = "/v1/responses";
          body = {
            model: instance.model,
            input: `Changed input ${index}`,
            prompt_cache_key: session,
          };
        } else if (source === "client_metadata") {
          path = "/v1/responses";
          body = {
            model: instance.model,
            input: `Changed input ${index}`,
            client_metadata: { session_id: session },
          };
        } else if (source === "anthropic_metadata") {
          path = "/v1/messages";
          body = {
            model: instance.model,
            max_tokens: 16,
            messages: [{ role: "user", content: `Changed input ${index}` }],
            metadata: { user_id: JSON.stringify({ session_id: session }) },
          };
        } else if (source === "x-codex-turn-metadata") {
          headers[source] = JSON.stringify({
            session_id: session,
            workspaces: "not-a-key",
          });
        } else headers[source] = session;
        const response = await instance.http.post(path, {
          headers,
          json: body,
        });
        expect(response.status).toBe(200);
        expect(instance.runtimes[selected]!.calls).toHaveLength(
          before[selected]! + 2,
        );
      }
    },
  );

  it("does not leak affinity controls into the runtime body", async () => {
    const instance = await makeCase("vllm");
    const response = await instance.http.post("/v1/responses", {
      headers: { ...instance.headers, "session-id": "lower-priority" },
      json: {
        model: instance.model,
        input: "Synthetic billing ticket",
        prompt_cache_key: "preferred-key",
        client_metadata: { session_id: "fallback-key" },
      },
    });
    expect(response.status).toBe(200);
    const body = instance.runtimes[0]!.calls[0]!;
    for (const field of ["session_id", "prompt_cache_key", "client_metadata"])
      expect(body).not.toHaveProperty(field);
  });

  it("rejects invalid explicit keys before dispatch and tolerates malformed optional metadata", async () => {
    const instance = await makeCase("vllm");
    for (const value of ["", "x".repeat(257), 123]) {
      const response = await instance.post({ prompt_cache_key: value });
      expectRejected(response, {
        code: "invalid_request",
        param: "prompt_cache_key",
      });
    }
    expect(instance.totalCalls()).toBe(0);
    const response = await instance.http.post(instance.path, {
      headers: {
        ...instance.headers,
        "x-codex-turn-metadata": "not-json",
        "x-session-id": ["duplicate-a", "duplicate-b"],
      },
      json: instance.body(),
    });
    expect(response.status).toBe(200);
  });
});
