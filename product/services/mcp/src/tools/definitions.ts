import type { ToolAnnotations } from "@modelcontextprotocol/sdk/types.js";

import {
  inlineReferences,
  operations,
  type JsonSchema,
  type Method,
  type OpenApiDocument,
  type OperationEntry,
} from "../openapi.js";
import { TOOL_CONFIG, type ArgumentConfig, type ToolConfig } from "./config.js";

// Filled from the caller's credential, never from the model.
export const CONTEXT_PARAMETERS = ["workspace_id"] as const;

export type ContextParameter = (typeof CONTEXT_PARAMETERS)[number];

export interface ToolArgument {
  name: string;
  field: string;
  location: "path" | "query" | "body";
}

export interface FixedArgument {
  field: string;
  location: ToolArgument["location"];
  value: unknown;
}

export interface ObjectSchema {
  type: "object";
  properties?: Record<string, JsonSchema>;
  required?: string[];
  [key: string]: unknown;
}

export interface ToolDefinition {
  name: string;
  title: string;
  description: string;
  method: Method;
  path: string;
  upstream: "api" | "inference";
  inputSchema: ObjectSchema & {
    properties: Record<string, JsonSchema>;
    required: string[];
    additionalProperties: false;
  };
  outputSchema?: ObjectSchema;
  arguments: ToolArgument[];
  fixed: FixedArgument[];
  annotations: ToolAnnotations;
}

type EnabledConfig = Extract<ToolConfig, { enabled: true }>;

interface Field extends ToolArgument {
  schema: JsonSchema;
  required: boolean;
}

const isContext = (name: string): name is ContextParameter =>
  (CONTEXT_PARAMETERS as readonly string[]).includes(name);

const annotations = (
  method: Method,
  title: string,
  inference: boolean,
): ToolAnnotations => ({
  title,
  readOnlyHint: method === "get",
  destructiveHint: method === "delete",
  idempotentHint: method !== "post" && method !== "patch",
  // A model call reaches a model; every other tool stays inside the workspace.
  openWorldHint: inference,
});

const withDescription = (
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

const isObjectSchema = (schema: JsonSchema): boolean => {
  if (schema.type === "object") return true;

  const choices = schema.anyOf ?? schema.oneOf;

  return (
    Array.isArray(choices) &&
    choices.length > 0 &&
    choices.every((choice) => isObjectSchema(choice as JsonSchema))
  );
};

const withoutExamples = (schema: unknown): unknown => {
  if (Array.isArray(schema)) return schema.map(withoutExamples);
  if (typeof schema !== "object" || schema === null) return schema;

  return Object.fromEntries(
    Object.entries(schema)
      .filter(([key]) => key !== "example")
      .map(([key, value]) => [key, withoutExamples(value)]),
  );
};

// MCP output schemas describe an object; an anyOf of object shapes qualifies once typed.
const outputSchema = (
  entry: OperationEntry,
  config: EnabledConfig,
  document: OpenApiDocument,
): ObjectSchema | undefined => {
  const response = Object.entries(entry.operation.responses ?? {}).find(
    ([status]) => /^2\d\d$/.test(status),
  )?.[1];
  const schema = config.output
    ? { $ref: `#/components/schemas/${config.output}` }
    : response?.content?.["application/json"]?.schema;
  if (!schema) return undefined;

  const inlined = withoutExamples(
    inlineReferences(schema, document),
  ) as JsonSchema;

  return isObjectSchema(inlined)
    ? ({ ...inlined, type: "object" } as ObjectSchema)
    : undefined;
};

const fields = (entry: OperationEntry, document: OpenApiDocument): Field[] => {
  const parameters = (entry.operation.parameters ?? []).flatMap(
    (parameter): Field[] =>
      (parameter.in === "path" || parameter.in === "query") &&
      !isContext(parameter.name)
        ? [
            {
              name: parameter.name,
              field: parameter.name,
              location: parameter.in,
              schema: withDescription(
                inlineReferences(
                  parameter.schema ?? {},
                  document,
                ) as JsonSchema,
                parameter.description,
              ),
              required: parameter.required === true,
            },
          ]
        : [],
  );
  const body = bodySchema(entry, document);
  const required = new Set(
    Array.isArray(body?.required) ? (body.required as string[]) : [],
  );
  const bodyFields = Object.entries(
    (body?.properties ?? {}) as Record<string, JsonSchema>,
  ).map(([field, schema]): Field => ({
    name: field,
    field,
    location: "body",
    schema,
    required: required.has(field),
  }));

  return [...parameters, ...bodyFields];
};

const buildTool = (
  entry: OperationEntry,
  config: EnabledConfig,
  document: OpenApiDocument,
): ToolDefinition => {
  const available = fields(entry, document);
  const configured: Record<string, ArgumentConfig> = config.arguments ?? {};

  for (const field of Object.keys(configured))
    if (!available.some((argument) => argument.field === field))
      throw new Error(`${config.name} configures unknown argument ${field}.`);

  const properties: Record<string, JsonSchema> = {};
  const required: string[] = [];
  const toolArguments: ToolArgument[] = [];
  const fixed: FixedArgument[] = [];

  for (const field of available) {
    const override = configured[field.field];
    const hidden =
      override?.hidden === true ||
      (config.onlyConfiguredArguments === true && !override);

    if (hidden) {
      if (field.required && override?.value === undefined)
        throw new Error(
          `${config.name} hides required argument ${field.field} without a value.`,
        );
      if (override?.value !== undefined)
        fixed.push({
          field: field.field,
          location: field.location,
          value: override.value,
        });
      continue;
    }

    const name = override?.name ?? field.name;
    if (Object.hasOwn(properties, name))
      throw new Error(`${config.name} has two arguments named ${name}.`);
    if (typeof field.schema.description !== "string")
      throw new Error(
        `Describe ${entry.operation.operationId}'s ${field.field} in the API contract.`,
      );

    properties[name] = field.schema;
    if (field.required || override?.required) required.push(name);
    toolArguments.push({ name, field: field.field, location: field.location });
  }

  const output = outputSchema(entry, config, document);

  return {
    name: config.name,
    title: config.title,
    description:
      config.description ??
      entry.operation.description ??
      entry.operation.summary ??
      config.title,
    method: entry.method,
    path: entry.path,
    upstream: config.inference ? "inference" : "api",
    inputSchema: {
      type: "object",
      properties,
      required,
      additionalProperties: false,
    },
    ...(output ? { outputSchema: output } : {}),
    arguments: toolArguments,
    fixed,
    annotations: annotations(
      entry.method,
      config.title,
      config.inference === true,
    ),
  };
};

export const buildTools = (
  document: OpenApiDocument,
  config: Partial<Record<string, ToolConfig>> = TOOL_CONFIG,
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

    return entry && toolConfig?.enabled
      ? [buildTool(entry, toolConfig, document)]
      : [];
  });

  const names = tools.map((tool) => tool.name);
  const duplicate = names.find((name, index) => names.indexOf(name) !== index);
  if (duplicate) throw new Error(`Two MCP tools are named ${duplicate}.`);

  return tools;
};
