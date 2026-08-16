import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { createApp, openApiDocument } from "../src/app.js";

const outputPath = resolve(import.meta.dirname, "../generated/openapi.json");
const document = createApp().getOpenAPI31Document(openApiDocument);
const serialized = `${JSON.stringify(document, null, 2)}\n`;

if (process.argv.includes("--check")) {
  const existing = await readFile(outputPath, "utf8").catch(() => "");
  if (existing !== serialized) {
    console.error(
      "generated/openapi.json is stale; run npm run openapi:generate",
    );
    process.exitCode = 1;
  }
} else {
  await writeFile(outputPath, serialized, "utf8");
}
