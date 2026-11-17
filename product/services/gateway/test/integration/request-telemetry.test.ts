import { GenerationSettledSchema } from "@gradiated/contracts";
import { describe, expect, it } from "vitest";

import { useCases } from "./case.js";
import { object } from "./json.js";

const { makeCase } = useCases();

describe("request metadata through real gateway settlement", () => {
  it.each([false, true])(
    "persists content-free structure and authoritative buckets for stream=%s",
    async (stream) => {
      const instance = await makeCase("vllm");
      const response = await instance.http.post(instance.path, {
        headers: {
          ...instance.headers,
          "x-gradiated-task-type": "code_edit",
          "user-agent": "opencode/1.0",
        },
        json: {
          ...instance.body(),
          stream,
          max_tokens: 16,
          messages: [
            {
              role: "user",
              content:
                "Please refactor this private-function.\n```python\ndef private_function(): return 42\n```",
            },
          ],
          tools: [
            {
              type: "function",
              function: {
                name: "private-tool",
                parameters: {
                  type: "object",
                  properties: { "private-property": { type: "string" } },
                },
              },
            },
          ],
          temperature: 0.7,
        },
      });
      expect(response.status).toBe(200);
      const properties = await instance.settled(response);
      const parsed = GenerationSettledSchema.parse({
        generation_id: response.headers["x-gradiated-generation-id"],
        properties,
      });
      expect(parsed.properties.event_schema_version).toBe(2);
      if (parsed.properties.event_schema_version !== 2)
        throw new Error("expected version 2");
      const metadata = parsed.properties.request_telemetry;
      expect(metadata).toMatchObject({
        schema_version: 1,
        protocol: "openai_chat",
        client: "opencode",
        traffic: "routed",
        kind: "tool_context",
        task_type: "code_edit",
        task_source: "caller",
        language_hint: "python",
        tool_definitions: 1,
        tool_schema: { properties: 1 },
        sampling: { temperature: 0.7 },
        output_limit_source: "caller",
      });
      expect(metadata?.effective_max_output_tokens).toBeGreaterThan(0);
      expect(metadata?.token_buckets?.input).toBeDefined();
      expect(metadata?.token_buckets?.output).toBeDefined();
      expect(JSON.stringify(metadata)).not.toContain("private-");
      expect(JSON.stringify(metadata)).not.toContain("private_function");
      expect(JSON.stringify(metadata)).not.toContain("return 42");
      const metrics = await instance.http.get("/metrics");
      expect(metrics.text).toContain(
        "gradiated_gateway_workload_requests_total",
      );
    },
  );

  it.each(["anthropic_messages", "openai_responses"])(
    "preserves original %s structure across protocol translation",
    async (protocol) => {
      const instance = await makeCase("vllm");
      const anthropic = protocol === "anthropic_messages";
      const response = await instance.http.post(
        anthropic ? "/v1/messages" : "/v1/responses",
        {
          headers: instance.headers,
          json: anthropic
            ? {
                model: instance.model,
                max_tokens: 16,
                messages: [
                  { role: "user", content: "Summarize this synthetic ticket" },
                ],
              }
            : {
                model: instance.model,
                input: "Summarize this synthetic ticket",
                max_output_tokens: 16,
              },
        },
      );
      expect(response.status).toBe(200);
      const properties = await instance.settled(response);
      expect(object(properties.request_telemetry)).toMatchObject({
        protocol,
        task_type: "summarization",
        task_source: "heuristic",
        requested_max_output_tokens: 16,
      });
    },
  );

  it("keeps native SystemOne state and question text out of metadata", async () => {
    const instance = await makeCase("kev");
    const response = await instance.http.post(instance.path, {
      headers: instance.headers,
      json: instance.body(),
    });
    expect(response.status).toBe(200);
    const properties = await instance.settled(response);
    const metadata = object(properties.request_telemetry);
    expect(metadata).toMatchObject({
      protocol: "system_one",
      kind: "system_one",
      task_type: "unknown",
    });
    expect(metadata.token_buckets).toBeDefined();
    expect(metadata).not.toHaveProperty("state");
    expect(metadata).not.toHaveProperty("questions");
  });
});
