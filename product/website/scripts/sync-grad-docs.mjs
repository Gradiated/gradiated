/* Copies what the training docs generate from the grad repository:
   the public operations of spec/openapi.yaml, the error codes grad-server
   answers with, and CHANGELOG.md.

     node scripts/sync-grad-docs.mjs --grad ../../../grad
     node scripts/sync-grad-docs.mjs --grad ../../../grad --check   # fail on drift

   Output: src/docs/training/generated/{api,error-codes,changelog,changelog-markdown}.json. */

import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Marked } from "marked";
import { parse } from "yaml";

const websiteRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = join(websiteRoot, "src/docs/training/generated");
const GITHUB = "https://github.com/Gradiated/grad/blob/main/";

/* Worker-only routes: grad's own trainer calls them with a worker token. */
const INTERNAL_TAGS = new Set(["TrainerJobs"]);
/* Codes only grad's workers or Gradiated Cloud's service routes can see. */
const INTERNAL_CODES = new Set([
  "artifact_checksum_mismatch",
  "artifact_required",
  "gpu_memory_exceeds_token",
  "insufficient_scope",
  "job_kind_forbidden",
  "lease_lost",
  "source_page_unavailable",
  "trainer_job_not_found",
  "unsupported_completion",
  "worker_auth_unavailable",
  "worker_host_mismatch",
  "wrong_job_kind",
]);
/* Codes chosen at runtime, which the patterns below can't see. */
const EXTRA_CODES = {
  cross_site_request: [403],
  host_not_allowed: [403],
  inference_error: [502],
};
const KEEP = [
  "type",
  "format",
  "description",
  "enum",
  "const",
  "default",
  "minimum",
  "maximum",
  "exclusiveMinimum",
  "minLength",
  "maxLength",
  "minItems",
  "maxItems",
  "pattern",
  "required",
  "$ref",
];

const args = process.argv.slice(2);
const gradArg = args[args.indexOf("--grad") + 1];
if (!args.includes("--grad") || !gradArg) {
  console.error("usage: sync-grad-docs.mjs --grad PATH [--check]");
  process.exit(2);
}
const grad = resolve(gradArg);
const check = args.includes("--check");

const refName = (ref) => ref.replace("#/components/schemas/", "");

/* A schema with only what the reference renders, and the names it uses. */
const trim = (schema, uses) => {
  if (Array.isArray(schema)) return schema.map((item) => trim(item, uses));
  if (!schema || typeof schema !== "object") return schema;

  const out = {};
  for (const key of KEEP) {
    if (schema[key] === undefined) continue;
    out[key] = key === "$ref" ? refName(schema[key]) : schema[key];
  }
  if (out.$ref) uses.add(out.$ref);

  if (schema.properties) {
    out.properties = Object.fromEntries(
      Object.entries(schema.properties).map(([name, value]) => [
        name,
        trim(value, uses),
      ]),
    );
  }
  for (const key of ["items", "additionalProperties"]) {
    if (schema[key] && typeof schema[key] === "object") {
      out[key] = trim(schema[key], uses);
    }
  }
  for (const key of ["oneOf", "anyOf", "allOf"]) {
    if (schema[key]) out[key] = trim(schema[key], uses);
  }
  return out;
};

const apiReference = () => {
  const spec = parse(readFileSync(join(grad, "spec/openapi.yaml"), "utf8"));
  const parameters = spec.components.parameters ?? {};
  const uses = new Set();
  const operations = [];

  for (const [path, item] of Object.entries(spec.paths)) {
    for (const [method, op] of Object.entries(item)) {
      if (!["get", "post", "put", "patch", "delete"].includes(method)) continue;
      const tag = op.tags?.[0] ?? "Other";
      if (INTERNAL_TAGS.has(tag)) continue;

      const params = (op.parameters ?? []).map((param) => {
        const resolved = param.$ref
          ? parameters[param.$ref.split("/").pop()]
          : param;
        return {
          name: resolved.name,
          in: resolved.in,
          required: Boolean(resolved.required),
          description: resolved.description ?? resolved.schema?.description,
          schema: trim(resolved.schema ?? {}, uses),
        };
      });

      const body = op.requestBody?.content?.["application/json"]?.schema;
      const success = Object.entries(op.responses).filter(([status]) =>
        status.startsWith("2"),
      );
      const responses = success.map(([status, response]) => ({
        status: Number(status),
        description: response.description,
        contentType: Object.keys(response.content ?? {})[0] ?? null,
        schema: (() => {
          const content = Object.values(response.content ?? {})[0];
          return content?.schema ? trim(content.schema, uses) : null;
        })(),
      }));

      operations.push({
        id: op.operationId,
        method: method.toUpperCase(),
        path,
        tag,
        summary: op.summary ?? "",
        description: op.description ?? "",
        params,
        body: body ? trim(body, uses) : null,
        bodyRequired: Boolean(op.requestBody?.required),
        responses,
        errors: Object.keys(op.responses)
          .filter((status) => !status.startsWith("2"))
          .map(Number),
      });
    }
  }

  const schemas = {};
  const queue = [...uses];
  while (queue.length) {
    const name = queue.shift();
    if (schemas[name]) continue;
    const found = new Set();
    schemas[name] = trim(spec.components.schemas[name], found);
    for (const next of found) if (!schemas[next]) queue.push(next);
  }

  return {
    version: spec.info.version,
    title: spec.info.title,
    operations,
    schemas: Object.fromEntries(
      Object.entries(schemas).sort(([a], [b]) => a.localeCompare(b)),
    ),
  };
};

const tsFiles = (dir) =>
  readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return tsFiles(path);
    return name.endsWith(".ts") && !name.endsWith(".test.ts") ? [path] : [];
  });

/* Every `code` grad-server can put in a problem+json body, with its statuses. */
const errorCodes = () => {
  const helpers = {
    conflict: 409,
    invalid: 422,
    forbidden: 403,
    unavailable: 501,
  };
  const codes = new Map();
  const add = (code, status) => {
    if (INTERNAL_CODES.has(code)) return;
    if (!codes.has(code)) codes.set(code, new Set());
    codes.get(code).add(Number(status));
  };

  for (const file of tsFiles(join(grad, "server/api/src"))) {
    const text = readFileSync(file, "utf8");
    for (const m of text.matchAll(
      /new ApiError\(\s*(\d{3}),\s*["`]([a-z][a-z0-9_]+)["`]/g,
    )) {
      add(m[2], m[1]);
    }
    for (const m of text.matchAll(
      /\b(conflict|invalid|forbidden|unavailable)\(\s*"([a-z][a-z0-9_]+)"/g,
    )) {
      add(m[2], helpers[m[1]]);
    }
    for (const m of text.matchAll(
      /problem(?:Response|Body)\(\s*(?:[\w.]+,\s*)?(\d{3}),\s*"([a-z][a-z0-9_]+)"/g,
    )) {
      add(m[2], m[1]);
    }
    // A helper whose code is a default parameter: (detail, code = "forbidden") => new ApiError(403, code, ...)
    for (const m of text.matchAll(
      /code = "([a-z][a-z0-9_]+)",?\s*\)[^=]*=>\s*new ApiError\(\s*(\d{3})/g,
    )) {
      add(m[1], m[2]);
    }
    for (const m of text.matchAll(/\bnotFound\(\s*"([a-z_]+)"/g)) {
      add(`${m[1]}_not_found`, 404);
    }
  }

  for (const [code, statuses] of Object.entries(EXTRA_CODES)) {
    for (const status of statuses) add(code, status);
  }

  return Object.fromEntries(
    [...codes]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([code, statuses]) => [code, [...statuses].sort()]),
  );
};

const changelog = () => {
  const source = readFileSync(join(grad, "CHANGELOG.md"), "utf8");
  const marked = new Marked({
    renderer: {
      link({ href, tokens }) {
        const absolute =
          /^[a-z]+:/i.test(href) || href.startsWith("#")
            ? href
            : GITHUB + href.replace(/^\.\//, "");
        return `<a href="${absolute}">${this.parser.parseInline(tokens)}</a>`;
      },
    },
  });

  const releases = [];
  for (const section of source.split(/^## /m).slice(1)) {
    const [heading, ...rest] = section.split("\n");
    const match = /^\[?([^\]\s]+)\]?(?:\s*-\s*(\d{4}-\d{2}-\d{2}))?/.exec(
      heading,
    );
    const body = rest.join("\n").trim();
    if (!match || !body || match[1] === "Unreleased") continue;
    releases.push({
      version: match[1],
      date: match[2] ?? null,
      html: marked.parse(body),
      markdown: body,
    });
  }
  return releases;
};

const releases = changelog();
/* The page ships the HTML to browsers; only prerender needs the Markdown. */
const outputs = {
  "api.json": apiReference(),
  "error-codes.json": { codes: errorCodes() },
  "changelog.json": {
    releases: releases.map(({ version, date, html }) => ({
      version,
      date,
      html,
    })),
  },
  "changelog-markdown.json": {
    releases: releases.map(({ version, date, markdown }) => ({
      version,
      date,
      markdown,
    })),
  },
};

let drift = false;
for (const [name, value] of Object.entries(outputs)) {
  const path = join(outDir, name);
  const text = `${JSON.stringify(value, null, 1)}\n`;
  let current = null;
  try {
    current = readFileSync(path, "utf8");
  } catch {
    // Not generated yet.
  }
  if (current === text) continue;
  if (check) {
    console.error(`${name} is out of date with ${grad}`);
    drift = true;
  } else {
    writeFileSync(path, text);
    console.log(`wrote ${path}`);
  }
}
process.exit(drift ? 1 : 0);
