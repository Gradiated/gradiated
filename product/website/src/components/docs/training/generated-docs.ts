import { documents, navigation } from "../../../pages/DocsPage";
import { ERROR_ENTRIES } from "./ErrorCodes";
import { curlFor } from "./ApiReference";
import {
  API,
  childrenOf,
  enumValues,
  operationAnchor,
  resolve,
  typeLabel,
  variantsOf,
} from "./api-schema";
import type { Schema } from "./api-schema";
import changelog from "../../../docs/training/generated/changelog-markdown.json";
import recorded from "../../../docs/training/generated/api-responses.json";

const RECORDED = (recorded as { responses: Record<string, { body: unknown }> })
  .responses;

const releaseAnchor = (version: string): string =>
  `v${version.replace(/\./g, "-")}`;

/* One field as a Markdown list item; inline objects and unions list their
   own fields indented below it, and named types point at "Schemas". */
const fieldLines = (
  name: string,
  schema: Schema,
  required: boolean,
  depth: number,
): string[] => {
  const resolved = resolve(schema);
  const values = enumValues(schema);
  const pad = "  ".repeat(depth);
  const extra = [
    required ? "required" : null,
    resolved.pattern ? `matches \`${resolved.pattern}\`` : null,
    values
      ? `one of ${values.map((v) => `\`${JSON.stringify(v)}\``).join(", ")}`
      : null,
  ].filter(Boolean);
  const description = schema.description ?? resolved.description;
  const lines = [
    `${pad}- \`${name}\` (${[typeLabel(schema), ...extra].join(", ")})${description ? `: ${description}` : ""}`,
  ];
  if (depth > 3 || schema.$ref) return lines;

  const target =
    resolved.items && !resolved.items.$ref ? resolve(resolved.items) : resolved;
  if (target.properties && !resolved.items?.$ref) {
    const required = new Set(target.required ?? []);
    for (const [child, value] of Object.entries(target.properties)) {
      lines.push(...fieldLines(child, value, required.has(child), depth + 1));
    }
  }
  for (const variant of values ? [] : variantsOf(schema)) {
    if (variant.$ref) continue;
    const shape = childrenOf(variant);
    if (!shape) continue;
    lines.push(`${pad}  - one shape:`);
    for (const [child, value] of Object.entries(shape.properties)) {
      lines.push(
        ...fieldLines(child, value, shape.required.includes(child), depth + 2),
      );
    }
  }
  return lines;
};

const schemasMarkdown = (): string =>
  [
    "## Schemas",
    "",
    "Every named type the endpoints above use, with all of its fields.",
    ...Object.entries(API.schemas).map(([name, schema]) => {
      const shape = childrenOf(schema);
      const variants = variantsOf(schema);
      const values = enumValues(schema);
      const body = shape
        ? Object.entries(shape.properties).flatMap(([field, value]) =>
            fieldLines(field, value, shape.required.includes(field), 0),
          )
        : values
          ? [
              `One of ${values.map((v) => `\`${JSON.stringify(v)}\``).join(", ")}.`,
            ]
          : variants.length
            ? variants.flatMap((variant, index) => {
                const part = childrenOf(variant);
                return [
                  `- shape ${index + 1}: ${typeLabel(variant)}`,
                  ...(part && !variant.$ref
                    ? Object.entries(part.properties).flatMap(
                        ([field, value]) =>
                          fieldLines(
                            field,
                            value,
                            part.required.includes(field),
                            1,
                          ),
                      )
                    : []),
                ];
              })
            : [typeLabel(schema)];
      return [
        `### ${name}`,
        "",
        ...(schema.description ? [schema.description, ""] : []),
        ...body,
      ].join("\n");
    }),
  ].join("\n\n");

const apiMarkdown = (): string =>
  API.operations
    .map((op) => {
      const body = op.body ? childrenOf(op.body) : null;
      const params = op.params
        .map(
          (param) =>
            `- \`${param.name}\` (${param.in}, ${typeLabel(param.schema)}${param.required ? ", required" : ""})${param.description ? `: ${param.description}` : ""}`,
        )
        .join("\n");
      const fields = body
        ? Object.entries(body.properties)
            .flatMap(([name, schema]) =>
              fieldLines(name, schema, body.required.includes(name), 0),
            )
            .join("\n")
        : "";
      return [
        `## ${op.method} ${op.path}`,
        "",
        op.summary,
        op.description ? `\n${op.description}` : "",
        params ? `\nParameters:\n\n${params}` : "",
        fields ? `\nBody:\n\n${fields}` : "",
        ...op.responses.map(
          (variant) =>
            `\nReturns ${variant.status}${variant.schema ? ` ${typeLabel(variant.schema)}` : ""}: ${variant.description}`,
        ),
        "",
        "```bash",
        curlFor(op),
        "```",
        ...(RECORDED[op.id]
          ? [
              "",
              "Response (recorded):",
              "",
              "```json",
              JSON.stringify(RECORDED[op.id]?.body, null, 2),
              "```",
            ]
          : []),
      ].join("\n");
    })
    .concat(schemasMarkdown())
    .join("\n\n");

const errorsMarkdown = (): string =>
  ERROR_ENTRIES.map(
    (entry) =>
      `- \`${entry.code}\` (${entry.statuses.join(", ")}): ${entry.means}${entry.fix ? ` Fix: ${entry.fix}` : ""}`,
  ).join("\n");

const changelogMarkdown = (): string =>
  (
    changelog as {
      releases: Array<{
        version: string;
        date: string | null;
        markdown: string;
      }>;
    }
  ).releases
    .map(
      (release) =>
        `## ${release.version}${release.date ? ` (${release.date})` : ""}\n\n${release.markdown}`,
    )
    .join("\n\n");

type SearchEntry = {
  path: string;
  title: string;
  heading?: string;
  text: string;
};

/* Entries for what the generated pages render: one per endpoint, error code
   and release, so search lands on the anchor itself. */
const generatedEntries = (): SearchEntry[] => [
  ...API.operations.map((op) => ({
    path: `${documents["training-api-reference"].path}#${operationAnchor(op)}`,
    title: documents["training-api-reference"].title,
    heading: `${op.method} ${op.path}`,
    text: `${op.summary} ${op.description} ${op.id}`,
  })),
  ...ERROR_ENTRIES.map((entry) => ({
    path: `${documents["training-errors"].path}#${entry.code}`,
    title: documents["training-errors"].title,
    heading: entry.code,
    text: `${entry.statuses.join(" ")} ${entry.means} ${entry.fix ?? ""}`,
  })),
  ...(
    changelog as { releases: Array<{ version: string; markdown: string }> }
  ).releases.map((release) => ({
    path: `${documents["training-changelog"].path}#${releaseAnchor(release.version)}`,
    title: documents["training-changelog"].title,
    heading: release.version,
    text: release.markdown.slice(0, 1200),
  })),
];

export const docsGenerated = () => ({
  groups: Object.fromEntries(
    navigation.flatMap((group) =>
      group.items.map((key) => [documents[key].path, group.heading]),
    ),
  ),
  markdown: {
    DocsApiReference: apiMarkdown(),
    DocsErrorCodes: errorsMarkdown(),
    DocsChangelog: changelogMarkdown(),
  },
  entries: generatedEntries(),
});
