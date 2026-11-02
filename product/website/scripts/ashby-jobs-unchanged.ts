// Is the live site built from the job list Ashby has now?
//
// Re-runs the job sync, then compares the public/ashby-jobs.sha256 it writes
// with the one the live site serves. Exits like `git diff --quiet`:
//   0  unchanged: nothing to redeploy
//   1  changed (or the live site has no hash yet): redeploy
//   2  could not tell (Ashby or the site unreachable)
//
// Used by vercel.json's ignoreCommand, so a deploy hook build is not skipped
// when only Ashby changed, and by .github/workflows/ashby-jobs.yml, which
// triggers that deploy hook.

import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

declare const process: {
  env: Record<string, string | undefined>;
  execPath: string;
  exit(code: number): never;
};

const SITE = process.env.SITE_URL ?? "https://www.gradiated.com";
const SYNC = fileURLToPath(new URL("./sync-ashby-jobs.ts", import.meta.url));
const HASH = new URL("../public/ashby-jobs.sha256", import.meta.url);

const sync = spawnSync(process.execPath, [SYNC], {
  stdio: "inherit",
  env: { ...process.env, ASHBY_SYNC_OPTIONAL: "" },
});
if (sync.status !== 0) {
  console.error("Ashby job sync failed; cannot tell whether jobs changed.");
  process.exit(2);
}
const ashby = (await readFile(HASH, "utf8")).trim();

let live: string;
try {
  const response = await fetch(`${SITE}/ashby-jobs.sha256`, {
    cache: "no-store",
  });
  // Deployed before the site published a hash: treat as changed.
  live = response.status === 404 ? "" : (await response.text()).trim();
  if (!response.ok && response.status !== 404) {
    throw new Error(`HTTP ${response.status}`);
  }
} catch (error) {
  console.error(
    `Could not read ${SITE}/ashby-jobs.sha256: ${(error as Error).message}`,
  );
  process.exit(2);
}

if (live === ashby) {
  console.log(`Ashby jobs unchanged (${ashby.slice(0, 12)}).`);
  process.exit(0);
}
console.log(
  `Ashby jobs changed: live ${live.slice(0, 12) || "none"}, Ashby ${ashby.slice(0, 12)}.`,
);
process.exit(1);
