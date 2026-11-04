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
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

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

/** Downloads PostHog's data files and imports them as modules. */
const fetchPostHogData = async (): Promise<Record<string, unknown>> => {
  const dir = await mkdtemp(join(tmpdir(), "posthog-compensation-"));
  try {
    const data: Record<string, unknown> = {};
    for (const [key, [file, exportName]] of Object.entries(FILES)) {
      const response = await fetch(`${SOURCE}/${file}.ts`);
      if (!response.ok) throw new Error(`${file}.ts: HTTP ${response.status}`);
      const path = join(dir, `${file}.ts`);
      await writeFile(path, await response.text());
      const module = await import(pathToFileURL(path).href);
      if (module[exportName] === undefined) {
        throw new Error(`${file}.ts no longer exports ${exportName}`);
      }
      data[key] = module[exportName];
    }
    return data;
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
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
