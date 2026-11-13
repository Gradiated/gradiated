import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

export type JsonSchema = { [key: string]: unknown };

export interface Parameter {
  name: string;
  in: "path" | "query" | "header" | "cookie";
  required?: boolean;
  description?: string;
  schema?: JsonSchema;
}

export interface Operation {
  operationId: string;
  summary?: string;
  description?: string;
  parameters?: Parameter[];
  requestBody?: {
    required?: boolean;
    content?: Record<string, { schema?: JsonSchema }>;
  };
  responses?: Record<
    string,
    { content?: Record<string, { schema?: JsonSchema }> }
  >;
}

export const METHODS = ["get", "post", "put", "patch", "delete"] as const;

export type Method = (typeof METHODS)[number];

export interface OpenApiDocument {
  paths: Record<string, Partial<Record<Method, Operation>>>;
  components?: { schemas?: Record<string, JsonSchema> };
}

export interface OperationEntry {
  method: Method;
  path: string;
  operation: Operation;
}

export const loadApiDocument = (): OpenApiDocument => {
  const require = createRequire(import.meta.url);
  const path = require.resolve("@gradiated/api/generated/client-openapi.json");

  return JSON.parse(readFileSync(path, "utf8")) as OpenApiDocument;
};

export const operations = (document: OpenApiDocument): OperationEntry[] =>
  Object.entries(document.paths).flatMap(([path, item]) =>
    METHODS.flatMap((method) => {
      const operation = item[method];

      return operation ? [{ method, path, operation }] : [];
    }),
  );

const REFERENCE_PREFIX = "#/components/schemas/";

// MCP clients expect a self-contained input schema, so component references are inlined.
export const inlineReferences = (
  schema: unknown,
  document: OpenApiDocument,
  resolving: readonly string[] = [],
): unknown => {
  if (Array.isArray(schema))
    return schema.map((item) => inlineReferences(item, document, resolving));
  if (typeof schema !== "object" || schema === null) return schema;

  const { $ref, ...rest } = schema as JsonSchema;
  if (typeof $ref === "string" && $ref.startsWith(REFERENCE_PREFIX)) {
    const name = $ref.slice(REFERENCE_PREFIX.length);
    const target = document.components?.schemas?.[name];
    if (!target || resolving.includes(name))
      throw new Error(`Cannot inline schema reference ${$ref}.`);

    return {
      ...(inlineReferences(target, document, [...resolving, name]) as object),
      ...rest,
    };
  }

  return foldAnnotations(
    Object.fromEntries(
      Object.entries(rest).map(([key, value]) => [
        key,
        inlineReferences(value, document, resolving),
      ]),
    ),
  );
};

const ANNOTATIONS = new Set(["description", "default", "example", "title"]);

const isAnnotation = (schema: unknown) =>
  typeof schema === "object" &&
  schema !== null &&
  Object.keys(schema).every((key) => ANNOTATIONS.has(key));

// A described reference is generated as allOf: [schema, { description }]; clients read it better merged.
const foldAnnotations = (schema: JsonSchema): JsonSchema => {
  const { allOf, ...rest } = schema;
  if (!Array.isArray(allOf)) return schema;

  const schemas = allOf.filter((member) => !isAnnotation(member));
  if (schemas.length !== 1) return schema;

  return Object.assign(
    {},
    schemas[0] as JsonSchema,
    ...allOf.filter(isAnnotation),
    rest,
  ) as JsonSchema;
};
