// Runs at the start of `pnpm build` (plain `node`, using its built-in type stripping).
//
// Our pay uses PostHog's system, so the compensation calculator on the
// Compensation handbook page uses PostHog's numbers. This pulls the data files
// behind PostHog's own calculator from the posthog.com repo and writes them to
// src/posthog-compensation.generated.json:
//   - sf_benchmark.ts     San Francisco benchmark per role (USD)
//   - level_modifier.ts   multiplier per level
//   - step_modifier.ts    [low, high] multiplier per step
//   - location_factor.ts  factor and currency per country and area
//   - currency.ts         USD exchange rates used for display
//
// It also writes public/posthog-compensation.sha256, a hash of the generated
// file, so the live site says which data it was built from.
// scripts/posthog-compensation-unchanged.ts compares that with PostHog's
// current data, and .github/workflows/posthog-compensation.yml redeploys
// weekly when they differ.
//
// If GitHub can't be reached the build keeps the committed JSON: slightly
// stale numbers are better than no deploy.

import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import ts from "typescript";

declare const process: {
  env: Record<string, string | undefined>;
  exit(code: number): never;
};

const SOURCE =
  "https://raw.githubusercontent.com/PostHog/posthog.com/master/src/components/CompensationCalculator/compensation_data";
const OUTPUT = new URL(
  "../src/posthog-compensation.generated.json",
  import.meta.url,
);
const HASH_OUTPUT = new URL(
  "../public/posthog-compensation.sha256",
  import.meta.url,
);

const FILES = {
  benchmarks: ["sf_benchmark", "sfBenchmark"],
  levels: ["level_modifier", "levelModifier"],
  steps: ["step_modifier", "stepModifier"],
  locations: ["location_factor", "locationFactor"],
  currencies: ["currency", "currencyData"],
} as const;

/* The downloaded files are parsed, never run: only plain literals (objects,
   arrays, strings, numbers) are accepted, so code in them can't execute
   during our build. */

/** Converts a literal expression to a value, rejecting anything else. */
const literalValue = (node: ts.Expression, file: string): unknown => {
  if (ts.isParenthesizedExpression(node) || ts.isAsExpression(node)) {
    return literalValue(node.expression, file);
  }
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  if (ts.isNumericLiteral(node)) return Number(node.text);
  if (
    ts.isPrefixUnaryExpression(node) &&
    node.operator === ts.SyntaxKind.MinusToken &&
    ts.isNumericLiteral(node.operand)
  ) {
    return -Number(node.operand.text);
  }
  if (node.kind === ts.SyntaxKind.TrueKeyword) return true;
  if (node.kind === ts.SyntaxKind.FalseKeyword) return false;
  if (node.kind === ts.SyntaxKind.NullKeyword) return null;
  if (ts.isArrayLiteralExpression(node)) {
    return node.elements.map((element) => literalValue(element, file));
  }
  if (ts.isObjectLiteralExpression(node)) {
    const object: Record<string, unknown> = {};
    for (const property of node.properties) {
      if (
        !ts.isPropertyAssignment(property) ||
        !(
          ts.isIdentifier(property.name) ||
          ts.isStringLiteral(property.name) ||
          ts.isNumericLiteral(property.name)
        )
      ) {
        throw new Error(`${file}.ts has a property that isn't plain data`);
      }
      object[property.name.text] = literalValue(property.initializer, file);
    }
    return object;
  }
  throw new Error(
    `${file}.ts has a ${ts.SyntaxKind[node.kind]} where data was expected`,
  );
};

/** Reads `export const <name> = <literal>` from a file's source text. */
const parseExport = (
  source: string,
  file: string,
  exportName: string,
): unknown => {
  const sourceFile = ts.createSourceFile(
    `${file}.ts`,
    source,
    ts.ScriptTarget.Latest,
  );
  for (const statement of sourceFile.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (
        ts.isIdentifier(declaration.name) &&
        declaration.name.text === exportName &&
        declaration.initializer
      ) {
        return literalValue(declaration.initializer, file);
      }
    }
  }
  throw new Error(`${file}.ts no longer exports ${exportName}`);
};

/** Downloads PostHog's data files and reads the data out of them. */
const fetchPostHogData = async (): Promise<Record<string, unknown>> => {
  const data: Record<string, unknown> = {};
  for (const [key, [file, exportName]] of Object.entries(FILES)) {
    const response = await fetch(`${SOURCE}/${file}.ts`);
    if (!response.ok) throw new Error(`${file}.ts: HTTP ${response.status}`);
    data[key] = parseExport(await response.text(), file, exportName);
  }
  return data;
};

let generated: string;
try {
  generated = `${JSON.stringify(await fetchPostHogData(), null, 2)}\n`;
  await writeFile(OUTPUT, generated);
  console.log("Synced compensation data from PostHog.");
} catch (error) {
  const reason = `Could not load compensation data from PostHog: ${(error as Error).message}`;
  // The unchanged check needs the real data; a build can fall back.
  if (process.env.POSTHOG_COMPENSATION_SYNC_REQUIRED === "1") {
    console.error(reason);
    process.exit(1);
  }
  console.warn(`${reason}. Keeping src/posthog-compensation.generated.json.`);
  generated = await readFile(OUTPUT, "utf8");
}

await writeFile(
  HASH_OUTPUT,
  `${createHash("sha256").update(generated).digest("hex")}\n`,
);
