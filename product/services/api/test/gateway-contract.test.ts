import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { createOpenApiDocument } from "../src/openapi.js";
import { createTestApp } from "./support.js";
import { chatRequest } from "../src/routes/gateway-schemas.js";

type Schema = {
  $ref?: string;
  description?: string;
  properties?: Record<string, Schema>;
  items?: Schema;
  additionalProperties?: boolean | Schema;
  allOf?: Schema[];
  anyOf?: Schema[];
  oneOf?: Schema[];
};

describe("gateway API reference", () => {
  it("accepts documented integer DeepSeek efforts and rejects out-of-range values", () => {
    const body = {
      model: "deepseek/deepseek-v4.1-flash",
      messages: [{ role: "user", content: "hello" }],
    };

    for (const reasoning_effort of [1, 25, 100, "none", "high"]) {
      expect(chatRequest.safeParse({ ...body, reasoning_effort }).success).toBe(
        true,
      );
    }

    for (const reasoning_effort of [0, 101, 1.5, true]) {
      expect(chatRequest.safeParse({ ...body, reasoning_effort }).success).toBe(
        false,
      );
    }
  });
  it("covers the Rust inference routes with workspace-key authentication", () => {
    const document = createOpenApiDocument();
    const source = readFileSync(
      new URL("../../gateway/src/http.rs", import.meta.url),
      "utf8",
    );
    const routes = source
      .split("fn inference_routes()")[1]!
      .split("pub fn router")[0]!;
    const matches = [
      ...routes.matchAll(/\.route\("([^"]+)", (get|post|endpoint)\(/g),
    ];
    expect(matches.length).toBe(6);

    for (const [, path, handler] of matches) {
      const method = handler === "get" ? "get" : "post";
      const operation = document.paths?.[`/v1${path}`]?.[method];
      expect(operation, `${method} /v1${path}`).toBeDefined();
      expect(operation?.security).toEqual([
        { InferenceBearer: [] },
        { InferenceApiKey: [] },
      ]);
      expect(operation?.responses?.["200"]).toBeDefined();
    }

    expect(document.paths?.["/models"]?.get).toBeDefined();
    for (const path of [
      "/v1/chat/completions",
      "/v1/messages",
      "/v1/responses",
    ]) {
      expect(document.paths?.[path]?.post?.responses?.["200"]).toHaveProperty(
        "content.text/event-stream",
      );
    }
    expect(
      document.paths?.["/v1/messages/count_tokens"]?.post?.responses?.["200"],
    ).not.toHaveProperty("content.text/event-stream");
  });

  it("describes every declared inference and catalog field, including referenced schemas", () => {
    const document = createOpenApiDocument();
    const schemas = document.components?.schemas as Record<string, Schema>;
    const visited = new Set<Schema>();
    const referenced = (schema: Schema): Schema | undefined =>
      schema.$ref ? schemas[schema.$ref.split("/").at(-1)!] : undefined;
    const hasDescription = (schema: Schema): boolean =>
      Boolean(
        schema.description?.trim() ||
        (referenced(schema) && hasDescription(referenced(schema)!)) ||
        schema.allOf?.some(hasDescription),
      );
    const visit = (schema: Schema, path: string) => {
      if (visited.has(schema)) return;

      visited.add(schema);
      const target = referenced(schema);
      if (target) visit(target, path);

      for (const [name, field] of Object.entries(schema.properties ?? {})) {
        expect(
          hasDescription(field),
          `${path}.${name} needs a description`,
        ).toBe(true);
        visit(field, `${path}.${name}`);
      }

      for (const child of [
        ...(schema.allOf ?? []),
        ...(schema.anyOf ?? []),
        ...(schema.oneOf ?? []),
      ])
        visit(child, path);
      if (schema.items) visit(schema.items, `${path}[]`);
      if (
        schema.additionalProperties &&
        typeof schema.additionalProperties === "object"
      )
        visit(schema.additionalProperties, `${path}.*`);
    };

    for (const [path, item] of Object.entries(document.paths ?? {})) {
      if (!path.startsWith("/v1/") && path !== "/models") continue;

      for (const operation of [item.get, item.post]) {
        if (!operation) continue;

        const body = operation.requestBody;
        if (body && "content" in body) {
          for (const media of Object.values(body.content))
            if (media.schema) visit(media.schema as Schema, path);
        }
        for (const response of Object.values(operation.responses ?? {})) {
          if (!("content" in response)) continue;

          for (const media of Object.values(
            (response.content ?? {}) as Record<string, { schema?: Schema }>,
          ))
            if (media.schema) visit(media.schema as Schema, `${path} response`);
        }
      }
    }
  });

  it("serves the unified document without installing gateway handlers in Hono", async () => {
    const app = createTestApp();
    const response = await app.request("/api/openapi.json");
    expect(await response.json()).toEqual(createOpenApiDocument());
    expect(await (await app.request("/docs")).text()).toContain(
      "Gradiated API",
    );

    for (const path of [
      "/v1/chat/completions",
      "/v1/messages",
      "/v1/responses",
      "/v1/messages/count_tokens",
    ]) {
      expect((await app.request(path, { method: "POST" })).status).toBe(404);
    }
  });
});
