import { documents, navigation } from "../../../pages/DocsPage";
import { ERROR_ENTRIES } from "./ErrorCodes";
import { curlFor } from "./ApiReference";
import { API, childrenOf, operationAnchor, typeLabel } from "./api-schema";
import changelog from "../../../docs/training/generated/changelog.json";

const releaseAnchor = (version: string): string =>
  `v${version.replace(/\./g, "-")}`;

const apiMarkdown = (): string =>
  API.operations
    .map((op) => {
      const body = op.body ? childrenOf(op.body) : null;
      const fields = body
        ? Object.entries(body.properties)
            .map(
              ([name, schema]) =>
                `- \`${name}\` (${typeLabel(schema)}${body.required.includes(name) ? ", required" : ""})${schema.description ? `: ${schema.description}` : ""}`,
            )
            .join("\n")
        : "";
      const response = op.responses[0];
      return [
        `## ${op.method} ${op.path}`,
        "",
        op.summary,
        op.description ? `\n${op.description}` : "",
        fields ? `\nBody:\n\n${fields}` : "",
        response
          ? `\nReturns ${response.status}${response.schema ? ` ${typeLabel(response.schema)}` : ""}: ${response.description}`
          : "",
        "",
        "```bash",
        curlFor(op),
        "```",
      ].join("\n");
    })
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
