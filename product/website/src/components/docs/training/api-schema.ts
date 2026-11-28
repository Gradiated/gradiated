import api from "../../../docs/training/generated/api.json";

/* The public operations of grad's spec/openapi.yaml, as synced by
   scripts/sync-grad-docs.mjs, and what the reference derives from them. */

export type Schema = {
  type?: string | string[];
  format?: string;
  description?: string;
  enum?: unknown[];
  const?: unknown;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
  pattern?: string;
  required?: string[];
  $ref?: string;
  properties?: Record<string, Schema>;
  items?: Schema;
  additionalProperties?: Schema | boolean;
  oneOf?: Schema[];
  anyOf?: Schema[];
  allOf?: Schema[];
};

export type Param = {
  name: string;
  in: "path" | "query" | "header";
  required: boolean;
  description?: string;
  schema: Schema;
};

export type Operation = {
  id: string;
  method: string;
  path: string;
  tag: string;
  summary: string;
  description: string;
  params: Param[];
  body: Schema | null;
  bodyRequired: boolean;
  responses: Array<{
    status: number;
    description: string;
    contentType: string | null;
    schema: Schema | null;
  }>;
  errors: number[];
};

export const API = api as unknown as {
  version: string;
  operations: Operation[];
  schemas: Record<string, Schema>;
};

export const TAG_ORDER = [
  "Datasets",
  "Runs",
  "Checkpoints",
  "Artifacts",
  "Evals",
  "Sources",
  "Secrets",
  "Models",
  "Keys",
  "Usage",
];

export const resolve = (schema: Schema | undefined): Schema => {
  let current = schema ?? {};
  for (let hops = 0; current.$ref && hops < 8; hops += 1) {
    current = { ...API.schemas[current.$ref], ...withoutRef(current) };
  }
  return current;
};

const withoutRef = (schema: Schema): Schema => {
  const { $ref: _ref, ...rest } = schema;
  return rest;
};

const types = (schema: Schema): string[] =>
  Array.isArray(schema.type) ? schema.type : schema.type ? [schema.type] : [];

export const isNullable = (schema: Schema): boolean => {
  const resolved = resolve(schema);
  return (
    types(resolved).includes("null") ||
    (resolved.anyOf ?? resolved.oneOf ?? []).some((option) =>
      types(resolve(option)).includes("null"),
    )
  );
};

/* A short type, like the one a reader would write: `string`, `Run`,
   `array of DatasetRecord`, `"sft" | "dpo"`. */
export const typeLabel = (schema: Schema): string => {
  const name = schema.$ref;
  const resolved = resolve(schema);
  const variants = (resolved.anyOf ?? resolved.oneOf ?? []).filter(
    (option) => !types(resolve(option)).includes("null"),
  );

  if (resolved.const !== undefined) return JSON.stringify(resolved.const);
  if (resolved.enum) return name ?? "enum";
  if (variants.length === 1 && variants[0]) return typeLabel(variants[0]);
  if (variants.length > 1) return name ?? "one of";

  const own = types(resolved).filter((type) => type !== "null");
  if (own.includes("array")) {
    return `array of ${resolved.items ? typeLabel(resolved.items) : "any"}`;
  }
  if (own.includes("object") || resolved.properties) {
    if (name) return name;
    if (!resolved.properties && resolved.additionalProperties) {
      const values =
        typeof resolved.additionalProperties === "object"
          ? typeLabel(resolved.additionalProperties)
          : "any";
      return `map of ${values}`;
    }
    return "object";
  }
  if (own.length) {
    return resolved.format && own[0] === "string"
      ? `string (${resolved.format})`
      : own.join(" or ");
  }
  return name ?? "any";
};

/* The fields a reader can expand under a property: an object's properties,
   an array's item properties, or each variant of a union. */
export const childrenOf = (
  schema: Schema,
): { properties: Record<string, Schema>; required: string[] } | null => {
  const resolved = resolve(schema);
  const target =
    types(resolved).includes("array") && resolved.items
      ? resolve(resolved.items)
      : resolved;
  const merged: Schema = target.allOf
    ? target.allOf.map(resolve).reduce<Schema>(
        (all, part) => ({
          properties: { ...all.properties, ...part.properties },
          required: [...(all.required ?? []), ...(part.required ?? [])],
        }),
        {},
      )
    : target;

  if (!merged.properties || !Object.keys(merged.properties).length) return null;
  return { properties: merged.properties, required: merged.required ?? [] };
};

export const variantsOf = (schema: Schema): Schema[] => {
  const resolved = resolve(schema);
  return (resolved.oneOf ?? resolved.anyOf ?? []).filter(
    (option) => !types(resolve(option)).includes("null"),
  );
};

export const constraints = (schema: Schema): string[] => {
  const resolved = resolve(schema);
  const out: string[] = [];
  const range = (min?: number, max?: number, unit = "") => {
    if (min !== undefined && max !== undefined) {
      out.push(`${min}–${max}${unit}`);
    } else if (min !== undefined) out.push(`≥ ${min}${unit}`);
    else if (max !== undefined) out.push(`≤ ${max}${unit}`);
  };

  if (resolved.exclusiveMinimum !== undefined) {
    out.push(`> ${resolved.exclusiveMinimum}`);
  }
  range(resolved.minimum, resolved.maximum);
  if (resolved.minLength !== undefined && resolved.minLength > 1) {
    range(resolved.minLength, resolved.maxLength, " chars");
  } else if (resolved.maxLength !== undefined) {
    out.push(`≤ ${resolved.maxLength} chars`);
  }
  if (resolved.maxItems !== undefined) out.push(`≤ ${resolved.maxItems} items`);
  if (resolved.default !== undefined) {
    out.push(`default ${JSON.stringify(resolved.default)}`);
  }
  return out;
};

export const enumValues = (schema: Schema): unknown[] | null => {
  const resolved = resolve(schema);
  if (resolved.enum) return resolved.enum;
  const variants = variantsOf(schema);
  const consts = variants.map((option) => resolve(option).const);
  return consts.length && consts.every((value) => value !== undefined)
    ? consts
    : null;
};

/* -- examples ---------------------------------------------------------------- */

/* grad-server ids are a prefix and 24 hex characters (server/api/src/ids.ts);
   a released artifact's id is its name@version. */
const ID_PREFIX: Record<string, string> = {
  Run: "run",
  EvalRun: "eval",
  EvalOutput: "evout",
  ArtifactImport: "imp",
  ImportJob: "imp",
  Checkpoint: "ckpt",
  Source: "src",
  Secret: "sec",
  ApiKey: "key",
  CreatedApiKey: "key",
  Dataset: "ds",
};

const STRING_EXAMPLES: Record<string, string> = {
  name: "support-prod",
  dataset: "support-prod",
  model: "qwen/qwen3-8b",
  base_model: "qwen/qwen3-8b",
  ref: "support-sft@3",
  sha256: "9f2c4e1ab0d3c5e7f9a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5",
  url: "https://storage.example.com/bundle.tar?X-Amz-Signature=…",
  content: "Count active users from yesterday.",
  role: "user",
  error: "…",
  detail: "…",
  message: "…",
};

const exampleId = (owner: string | undefined): string =>
  owner === "Artifact"
    ? "support-sft@2026-11-28-1"
    : `${(owner && ID_PREFIX[owner]) ?? "obj"}_3f9c0a1b2c3d4e5f60718293`;

/* A plausible value for a schema, filled from its defaults, enums and the
   field's name. Required fields only, when `requiredOnly`. */
export const example = (
  schema: Schema,
  options: {
    field?: string;
    owner?: string;
    depth?: number;
    requiredOnly?: boolean;
  } = {},
): unknown => {
  const { field, owner, depth = 0, requiredOnly = false } = options;
  const resolved = resolve(schema);
  const name = schema.$ref ?? owner;

  if (resolved.const !== undefined) return resolved.const;
  if (resolved.default !== undefined && resolved.default !== null) {
    return resolved.default;
  }
  if (resolved.enum?.length) return resolved.enum[0];

  const variants = variantsOf(schema);
  if (variants.length && variants[0]) {
    return example(variants[0], { ...options, depth });
  }
  if (resolved.allOf?.length) {
    return Object.assign(
      {},
      ...resolved.allOf.map((part) => example(part, { ...options, depth })),
    );
  }

  const own = types(resolved).filter((type) => type !== "null");
  if (own.includes("array")) {
    if (depth > 4 || !resolved.items) return [];
    return [example(resolved.items, { field, depth: depth + 1, requiredOnly })];
  }
  if (own.includes("object") || resolved.properties) {
    if (depth > 4 || !resolved.properties) return {};
    const required = new Set(resolved.required ?? []);
    return Object.fromEntries(
      Object.entries(resolved.properties)
        .filter(([key]) => !requiredOnly || required.has(key))
        .map(([key, value]) => [
          key,
          example(value, {
            field: key,
            owner: name,
            depth: depth + 1,
            requiredOnly,
          }),
        ]),
    );
  }
  if (own.includes("integer") || own.includes("number")) {
    return resolved.minimum ?? resolved.exclusiveMinimum ?? 0;
  }
  if (own.includes("boolean")) return false;
  if (own.includes("string")) {
    if (resolved.format === "date-time") return "2026-11-28T09:30:00.000Z";
    if (resolved.format === "uri") return "https://example.com";
    if (field === "id") return exampleId(owner);
    if (field === "workspace_id") return "ws_8d2e4f6a1b3c5d7e9f0a2b4c";
    if (field === "artifact_id") return exampleId("Artifact");
    if (field?.endsWith("_id")) {
      const kind = field.replace(/_id$/, "");
      const key = [...Object.keys(ID_PREFIX), "Artifact"].find(
        (type) => type.toLowerCase() === kind.replace(/_/g, ""),
      );
      return exampleId(key);
    }
    if (field?.endsWith("_at")) return "2026-11-28T09:30:00.000Z";
    if (field?.endsWith("_name")) return "support-prod";
    return (field && STRING_EXAMPLES[field]) ?? "string";
  }
  if (isNullable(schema)) return null;
  return null;
};

const PATH_EXAMPLES: Record<string, string> = {
  name: "support-prod",
  holder: "inference:support-v3",
};

export const pathExample = (op: Operation, param: string): string => {
  if (PATH_EXAMPLES[param]) return PATH_EXAMPLES[param];
  const owner: Record<string, string> = {
    Runs: "Run",
    Checkpoints: op.path.startsWith("/v1/runs") ? "Run" : "Checkpoint",
    Artifacts: op.path.startsWith("/v1/artifact-imports")
      ? "ArtifactImport"
      : "Artifact",
    Evals: "EvalRun",
    Sources: "Source",
    Keys: "ApiKey",
    Datasets: "ImportJob",
  };
  return exampleId(owner[op.tag]);
};

export const operationAnchor = (op: Operation): string =>
  op.id.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);

export const tagAnchor = (tag: string): string => tag.toLowerCase();
