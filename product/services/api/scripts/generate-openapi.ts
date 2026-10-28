import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { createOpenApiDocuments } from "../src/openapi.js";

const documents = createOpenApiDocuments();
const outputs = [
  { path: "../generated/openapi.json", document: documents.public },
  { path: "../generated/client-openapi.json", document: documents.client },
];

for (const output of outputs) {
  const outputPath = resolve(import.meta.dirname, output.path);
  const serialized = `${JSON.stringify(output.document, null, 2)}\n`;

  if (!process.argv.includes("--check")) {
    await writeFile(outputPath, serialized, "utf8");
    continue;
  }

  const existing = await readFile(outputPath, "utf8").catch(() => "");
  if (existing !== serialized) {
    console.error(
      `${output.path.slice(3)} is stale; run pnpm --filter @gradiated/api openapi:generate`,
    );
    process.exitCode = 1;
  }
}
