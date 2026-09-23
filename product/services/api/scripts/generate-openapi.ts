import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { createOpenApiDocument } from "../src/openapi.js";

const outputPath = resolve(import.meta.dirname, "../generated/openapi.json");
const document = createOpenApiDocument();
const serialized = `${JSON.stringify(document, null, 2)}\n`;

if (process.argv.includes("--check")) {
  const existing = await readFile(outputPath, "utf8").catch(() => "");
  if (existing !== serialized) {
    console.error(
      "generated/openapi.json is stale; run pnpm --filter @gradiated/api openapi:generate",
    );
    process.exitCode = 1;
  }
} else {
  await writeFile(outputPath, serialized, "utf8");
}
