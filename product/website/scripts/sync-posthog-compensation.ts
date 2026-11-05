// Runs at the start of `pnpm build`. Copies the data behind PostHog's
// compensation calculator into src/posthog-compensation.generated.json, and
// its hash into public/posthog-compensation.sha256 for the weekly check.

import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";

declare const process: {
  env: Record<string, string | undefined>;
  exit(code: number): never;
};

const REPO = "PostHog/posthog.com";
const DATA_PATH = "src/components/CompensationCalculator/compensation_data";
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

const ESCAPES: Record<string, string> = { n: "\n", r: "\r", t: "\t" };

// The files are PostHog's code, so they're parsed rather than imported: only
// plain literals are accepted, and nothing in them runs during our build.
// Vercel's ignored-build step runs this before installing packages, so it
// can't use a parser package.
const parseExport = (source: string, file: string, name: string): unknown => {
  const start = new RegExp(`export\\s+const\\s+${name}\\b[^=]*=`).exec(source);
  if (!start) throw new Error(`${file}.ts no longer exports ${name}`);
  let i = start.index + start[0].length;

  const fail = (): never => {
    throw new Error(`${file}.ts has something other than data at ${i}`);
  };
  const match = (pattern: RegExp): string | undefined => {
    pattern.lastIndex = i;
    const found = pattern.exec(source);
    if (!found) return undefined;
    i += found[0].length;
    return found[0];
  };
  const skip = (): void => {
    while (match(/\s+|\/\/[^\n]*|\/\*[\s\S]*?\*\//y) !== undefined);
  };
  const expect = (char: string): void => {
    skip();
    if (source[i] !== char) fail();
    i += 1;
  };
  const string = (): string => {
    const quote = source[i++];
    let text = "";
    while (source[i] !== quote) {
      if (i >= source.length || source[i] === "\n") fail();
      if (source[i] === "\\") {
        i += 1;
        if (source[i] === "u") {
          text += String.fromCharCode(parseInt(source.slice(i + 1, i + 5), 16));
          i += 5;
          continue;
        }
        text += ESCAPES[source[i]] ?? source[i];
      } else {
        text += source[i];
      }
      i += 1;
    }
    i += 1;
    return text;
  };
  const key = (): string => {
    if (source[i] === "'" || source[i] === '"') return string();
    return match(/[A-Za-z_$][\w$]*|\d+/y) ?? fail();
  };
  const list = <T>(close: string, item: () => T): T[] => {
    const items: T[] = [];
    for (;;) {
      skip();
      if (source[i] === close) break;
      items.push(item());
      skip();
      if (source[i] !== ",") break;
      i += 1;
    }
    expect(close);
    return items;
  };
  const value = (): unknown => {
    skip();
    const char = source[i];
    if (char === "'" || char === '"') return string();
    if (char === "[") {
      i += 1;
      return list("]", value);
    }
    if (char === "{") {
      i += 1;
      return Object.fromEntries(
        list("}", () => {
          const name = key();
          expect(":");
          return [name, value()];
        }),
      );
    }
    const number = match(/-?\d+(\.\d+)?([eE][+-]?\d+)?\b/y);
    if (number !== undefined) return Number(number);
    const word = match(/true|false|null/y);
    if (word !== undefined) return JSON.parse(word);
    return fail();
  };

  return value();
};

// One commit for every file, so a push to master mid-sync can't mix versions.
const masterCommit = async (): Promise<string> => {
  const response = await fetch(
    `https://api.github.com/repos/${REPO}/commits/master`,
    { headers: { Accept: "application/vnd.github.sha" } },
  );
  if (!response.ok) throw new Error(`master: HTTP ${response.status}`);
  const sha = (await response.text()).trim();
  if (!/^[0-9a-f]{40}$/.test(sha)) throw new Error("master: no commit SHA");
  return sha;
};

const fetchPostHogData = async (): Promise<Record<string, unknown>> => {
  const sha = await masterCommit();
  const data: Record<string, unknown> = {};
  for (const [key, [file, name]] of Object.entries(FILES)) {
    const response = await fetch(
      `https://raw.githubusercontent.com/${REPO}/${sha}/${DATA_PATH}/${file}.ts`,
    );
    if (!response.ok) throw new Error(`${file}.ts: HTTP ${response.status}`);
    data[key] = parseExport(await response.text(), file, name);
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
  // The weekly check needs real data; a build can fall back to the committed copy.
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
