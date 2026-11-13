import { describe, expect, it } from "vitest";

import { loadApiDocument, type OpenApiDocument } from "../src/openapi.js";
import type { ToolConfig } from "../src/tools/config.js";
import { buildTools } from "../src/tools/definitions.js";

const document: OpenApiDocument = {
  paths: {
    "/api/v1/workspaces/{workspace_id}/tasks/{task}": {
      patch: {
        operationId: "updateTask",
        summary: "Update task",
        description: "Changes a task's settings.",
        parameters: [
          { name: "workspace_id", in: "path", required: true, schema: {} },
          {
            name: "task",
            in: "path",
            required: true,
            description: "The task's name.",
            schema: { type: "string" },
          },
          {
            name: "ref",
            in: "query",
            schema: { type: "string", description: "A reference." },
          },
        ],
        requestBody: {
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/UpdateTask" },
            },
          },
        },
        responses: {
          "200": {
            content: {
              "application/json": {
                schema: {
                  anyOf: [
                    { $ref: "#/components/schemas/Task" },
                    { type: "object", properties: {} },
                  ],
                },
              },
            },
          },
        },
      },
    },
  },
  components: {
    schemas: {
      UpdateTask: {
        type: "object",
        properties: {
          judge: { $ref: "#/components/schemas/Judge" },
          stream: { type: "boolean", description: "Streams." },
        },
        required: ["judge"],
      },
      Judge: { type: "string", description: "Judge model." },
      Task: { type: "object", properties: { name: { type: "string" } } },
    },
  },
};

const tool = (config: Partial<Extract<ToolConfig, { enabled: true }>> = {}) =>
  buildTools(document, {
    updateTask: {
      enabled: true,
      name: "update_task",
      title: "Update task",
      ...config,
    },
  });

describe("buildTools", () => {
  it("builds the configured tools from the API document", () => {
    const tools = buildTools(loadApiDocument());

    expect(tools.map(({ name }) => name)).toEqual([
      "whoami",
      "list_models",
      "call_model",
      "get_usage",
      "list_generations",
      "get_generation",
      "list_tasks",
      "get_task",
      "update_task",
      "list_task_versions",
      "get_task_version",
      "promote_task_version",
      "list_task_version_files",
      "read_task_version_file",
      "get_adapter_configuration",
    ]);
    for (const tool of tools) {
      expect(tool.name).toMatch(/^[a-z][a-z0-9_]{0,63}$/);
      expect(tool.description).not.toBe("");
      expect(tool.outputSchema?.type).toBe("object");
      expect(Object.keys(tool.inputSchema.properties)).not.toContain(
        "workspace_id",
      );
      expect(
        Object.keys(tool.inputSchema.properties).filter((name) =>
          name.endsWith("_id"),
        ),
        `${tool.name} takes names, not IDs`,
      ).toEqual(
        tool.name === "list_generations"
          ? ["api_key_id"]
          : tool.name === "get_generation"
            ? ["generation_id"]
            : tool.name === "get_adapter_configuration"
              ? ["model_id"]
              : tool.name === "update_task"
                ? ["base_model_id", "comparison_model_id", "judge_model_id"]
                : [],
      );
    }
  });

  it("offers call_model only its messages and sampling settings, never streaming", () => {
    const callModel = buildTools(loadApiDocument()).find(
      ({ name }) => name === "call_model",
    )!;

    expect(Object.keys(callModel.inputSchema.properties).sort()).toEqual([
      "max_completion_tokens",
      "messages",
      "model",
      "reasoning_effort",
      "response_format",
      "seed",
      "stop",
      "temperature",
      "top_p",
    ]);
    expect(callModel.inputSchema.required).toEqual(["model", "messages"]);
    expect(callModel.fixed).toEqual([
      { field: "stream", location: "body", value: false },
    ]);
    expect(callModel).toMatchObject({
      upstream: "inference",
      annotations: { readOnlyHint: false, openWorldHint: true },
    });
  });

  it("flattens path, query and body fields, renames arguments and inlines references", () => {
    expect(
      tool({ arguments: { task: { name: "task_name" } } })[0],
    ).toMatchObject({
      description: "Changes a task's settings.",
      inputSchema: {
        properties: {
          task_name: { type: "string", description: "The task's name." },
          ref: { type: "string", description: "A reference." },
          judge: { type: "string", description: "Judge model." },
        },
        required: ["task_name", "judge"],
        additionalProperties: false,
      },
      arguments: [
        { name: "task_name", field: "task", location: "path" },
        { name: "ref", field: "ref", location: "query" },
        { name: "judge", field: "judge", location: "body" },
        { name: "stream", field: "stream", location: "body" },
      ],
      annotations: { readOnlyHint: false, destructiveHint: false },
    });
  });

  it("describes the response as an object output schema", () => {
    expect(tool()[0]!.outputSchema).toEqual({
      type: "object",
      anyOf: [
        { type: "object", properties: { name: { type: "string" } } },
        { type: "object", properties: {} },
      ],
    });
  });

  it("hides arguments, fixes their values and requires a stand-in field", () => {
    const [built] = tool({
      onlyConfiguredArguments: true,
      arguments: {
        task: {},
        judge: {},
        ref: { required: true },
        stream: { hidden: true, value: false },
      },
    });

    expect(built!.inputSchema.required).toEqual(["task", "ref", "judge"]);
    expect(built!.arguments.map(({ name }) => name)).toEqual([
      "task",
      "ref",
      "judge",
    ]);
    expect(built!.fixed).toEqual([
      { field: "stream", location: "body", value: false },
    ]);
    expect(
      tool({ arguments: { ref: { hidden: true } } })[0]!.arguments.map(
        ({ name }) => name,
      ),
    ).toEqual(["task", "judge", "stream"]);
  });

  it("omits disabled operations", () => {
    expect(
      buildTools(document, { updateTask: { enabled: false, reason: "No." } }),
    ).toEqual([]);
  });

  it.each([
    [{}, "Configure MCP tools for updateTask."],
    [
      {
        updateTask: { enabled: false, reason: "No." },
        removedOperation: { enabled: false, reason: "No." },
      },
      "Remove MCP tool config for removedOperation.",
    ],
    [
      {
        updateTask: {
          enabled: true,
          name: "update_task",
          title: "Update task",
          arguments: { missing: { name: "other" } },
        },
      },
      "update_task configures unknown argument missing.",
    ],
    [
      {
        updateTask: {
          enabled: true,
          name: "update_task",
          title: "Update task",
          arguments: { task: { name: "judge" } },
        },
      },
      "update_task has two arguments named judge.",
    ],
    [
      {
        updateTask: {
          enabled: true,
          name: "update_task",
          title: "Update task",
          arguments: { judge: { hidden: true } },
        },
      },
      "update_task hides required argument judge without a value.",
    ],
  ] as const)("rejects inconsistent config %#", (config, message) => {
    expect(() => buildTools(document, config)).toThrow(message);
  });

  it("requires every offered argument to be described in the API contract", () => {
    const undescribed = structuredClone(document);
    delete undescribed.components!.schemas!.Judge!.description;

    expect(() =>
      buildTools(undescribed, {
        updateTask: { enabled: true, name: "update_task", title: "Update" },
      }),
    ).toThrow("Describe updateTask's judge in the API contract.");
  });
});
