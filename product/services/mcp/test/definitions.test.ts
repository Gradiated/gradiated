import { describe, expect, it } from "vitest";

import { loadApiDocument, type OpenApiDocument } from "../src/openapi.js";
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
            schema: { type: "string" },
          },
        ],
        requestBody: {
          content: {
            "application/json": {
              schema: { $ref: "#/components/schemas/UpdateTask" },
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
        properties: { judge: { $ref: "#/components/schemas/Judge" } },
        required: ["judge"],
      },
      Judge: { type: "string", description: "Judge model." },
    },
  },
};

describe("buildTools", () => {
  it("configures every operation in the API document", () => {
    const tools = buildTools(loadApiDocument());

    expect(tools.map(({ name }) => name)).toContain("list_tasks");
    for (const tool of tools) {
      expect(tool.name).toMatch(/^[a-z][a-z0-9_]{0,63}$/);
      expect(tool.description).not.toBe("");
      expect(Object.keys(tool.inputSchema.properties)).not.toContain(
        "workspace_id",
      );
    }
  });

  it("flattens path and body fields, renames arguments and inlines references", () => {
    const [tool] = buildTools(document, {
      updateTask: {
        enabled: true,
        name: "update_task",
        title: "Update task",
        arguments: { task: { name: "task_name", description: "Task name." } },
      },
    });

    expect(tool).toMatchObject({
      description: "Changes a task's settings.",
      inputSchema: {
        properties: {
          task_name: { type: "string", description: "Task name." },
          judge: { type: "string", description: "Judge model." },
        },
        required: ["task_name", "judge"],
        additionalProperties: false,
      },
      arguments: [
        { name: "task_name", field: "task", location: "path" },
        { name: "judge", field: "judge", location: "body" },
      ],
      annotations: { readOnlyHint: false, destructiveHint: false },
    });
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
  ] as const)("rejects inconsistent config %#", (config, message) => {
    expect(() => buildTools(document, config)).toThrow(message);
  });
});
