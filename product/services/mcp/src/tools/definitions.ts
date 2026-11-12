import type { ToolAnnotations } from "@modelcontextprotocol/sdk/types.js";

import {
  inlineReferences,
  operations,
  type JsonSchema,
  type Method,
  type OpenApiDocument,
  type OperationEntry,
} from "../openapi.js";
import { TOOL_CONFIG, type ToolConfig } from "./config.js";

// Filled from the caller's credential, never from the model.
export const CONTEXT_PARAMETERS = ["workspace_id"] as const;

export type ContextParameter = (typeof CONTEXT_PARAMETERS)[number];

export interface ToolArgument {
  name: string;
  field: string;
  location: "path" | "query" | "body";
}

export interface ToolDefinition {
  name: string;
  title: string;
  description: string;
  method: Method;
  path: string;
  inputSchema: {
    type: "object";
    properties: Record<string, JsonSchema>;
    required: string[];
    additionalProperties: false;
  };
  arguments: ToolArgument[];
  annotations: ToolAnnotations;
}

const isContext = (name: string): name is ContextParameter =>
  (CONTEXT_PARAMETERS as readonly string[]).includes(name);

const annotations = (method: Method, title: string): ToolAnnotations => ({
  title,
  readOnlyHint: method === "get",
  destructiveHint: method === "delete",
  idempotentHint: method !== "post" && method !== "patch",
  openWorldHint: false,
});

const describe = (
  schema: JsonSchema,
  description: string | undefined,
): JsonSchema => (description ? { ...schema, description } : schema);

const bodySchema = (
  entry: OperationEntry,
  document: OpenApiDocument,
): JsonSchema | undefined => {
  const schema =
    entry.operation.requestBody?.content?.["application/json"]?.schema;
  if (!schema) return undefined;

  const inlined = inlineReferences(schema, document) as JsonSchema;
  if (inlined.type !== "object" || typeof inlined.properties !== "object")
    throw new Error(
      `${entry.operation.operationId} has a JSON body that is not an object.`,
    );

  return inlined;
};

const buildTool = (
  entry: OperationEntry,
  config: Extract<ToolConfig, { enabled: true }>,
  document: OpenApiDocument,
): ToolDefinition => {
  const { operation } = entry;
  const fields: (ToolArgument & { schema: JsonSchema; required: boolean })[] =
    [];

  for (const parameter of operation.parameters ?? []) {
    if (parameter.in !== "path" && parameter.in !== "query") continue;
    if (isContext(parameter.name)) continue;

    fields.push({
      name: parameter.name,
      field: parameter.name,
      location: parameter.in,
      schema: describe(
        inlineReferences(parameter.schema ?? {}, document) as JsonSchema,
        parameter.description,
      ),
      required: parameter.required === true,
    });
  }

  const body = bodySchema(entry, document);
  const bodyRequired = new Set(
    Array.isArray(body?.required) ? (body.required as string[]) : [],
  );
  for (const [field, schema] of Object.entries(
    (body?.properties ?? {}) as Record<string, JsonSchema>,
  )) {
    fields.push({
      name: field,
      field,
      location: "body",
      schema,
      required: bodyRequired.has(field),
    });
  }

  const configured = config.arguments ?? {};
  for (const field of Object.keys(configured)) {
    if (!fields.some((argument) => argument.field === field))
      throw new Error(`${config.name} configures unknown argument ${field}.`);
  }

  const properties: Record<string, JsonSchema> = {};
  const required: string[] = [];
  const toolArguments: ToolArgument[] = [];
  for (const field of fields) {
    const override = configured[field.field];
    const name = override?.name ?? field.name;
    if (Object.hasOwn(properties, name))
      throw new Error(`${config.name} has two arguments named ${name}.`);

    properties[name] = describe(
      field.schema,
      override?.description ?? (field.schema.description as string),
    );
    if (field.required) required.push(name);
    toolArguments.push({ name, field: field.field, location: field.location });
  }

  return {
    name: config.name,
    title: config.title,
    description:
      config.description ??
      operation.description ??
      operation.summary ??
      config.title,
    method: entry.method,
    path: entry.path,
    inputSchema: {
      type: "object",
      properties,
      required,
      additionalProperties: false,
    },
    arguments: toolArguments,
    annotations: annotations(entry.method, config.title),
  };
};

export const buildTools = (
  document: OpenApiDocument,
  config: Record<string, ToolConfig> = TOOL_CONFIG,
): ToolDefinition[] => {
  const entries = operations(document);
  const missing = entries
    .map(({ operation }) => operation.operationId)
    .filter((id) => !Object.hasOwn(config, id));
  if (missing.length)
    throw new Error(`Configure MCP tools for ${missing.join(", ")}.`);

  const stale = Object.keys(config).filter(
    (id) => !entries.some(({ operation }) => operation.operationId === id),
  );
  if (stale.length)
    throw new Error(`Remove MCP tool config for ${stale.join(", ")}.`);

  // Tools are listed in config order, which groups them by subject.
  const tools = Object.entries(config).flatMap(([id, toolConfig]) => {
    const entry = entries.find(({ operation }) => operation.operationId === id);

    return entry && toolConfig.enabled
      ? [buildTool(entry, toolConfig, document)]
      : [];
  });

  const names = tools.map((tool) => tool.name);
  const duplicate = names.find((name, index) => names.indexOf(name) !== index);
  if (duplicate) throw new Error(`Two MCP tools are named ${duplicate}.`);

  return tools;
};
