import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const CRATES_IO = "registry+https://github.com/rust-lang/crates.io-index";
export const MIN_AGE_MS = 7 * 24 * 60 * 60 * 1000;

export const indexPath = (name) => {
  const crate = name.toLowerCase();
  if (crate.length <= 2) return `${crate.length}/${crate}`;
  if (crate.length === 3) return `3/${crate[0]}/${crate}`;
  return `${crate.slice(0, 2)}/${crate.slice(2, 4)}/${crate}`;
};

export const lockedCrates = (lockfile) =>
  lockfile
    .split("[[package]]")
    .slice(1)
    .map((block) => ({
      name: block.match(/^name = "([^"]+)"/m)?.[1],
      version: block.match(/^version = "([^"]+)"/m)?.[1],
      source: block.match(/^source = "([^"]+)"/m)?.[1],
    }))
    .filter((crate) => crate.source === CRATES_IO);

export const tooYoung = (pubtime, now, minAge = MIN_AGE_MS) =>
  pubtime !== undefined && now - Date.parse(pubtime) < minAge;

// Index entries published before Cargo 1.94 have no pubtime and are old enough.
export const pubtimes = (indexBody) =>
  new Map(
    indexBody
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line))
      .map((entry) => [entry.vers, entry.pubtime]),
  );

const fetchPubtimes = async (name) => {
  const response = await fetch(`https://index.crates.io/${indexPath(name)}`);
  if (!response.ok)
    throw new Error(`index.crates.io ${name}: HTTP ${response.status}`);
  return pubtimes(await response.text());
};

const inBatches = async (items, size, run) => {
  const results = [];
  for (let start = 0; start < items.length; start += size)
    results.push(
      ...(await Promise.all(items.slice(start, start + size).map(run))),
    );
  return results;
};

export const check = async (lockfiles, now = Date.now()) => {
  const locked = lockfiles.flatMap((path) =>
    lockedCrates(readFileSync(path, "utf8")).map((crate) => ({
      ...crate,
      path,
    })),
  );
  const names = [...new Set(locked.map((crate) => crate.name))];
  const index = new Map(
    await inBatches(names, 16, async (name) => [
      name,
      await fetchPubtimes(name),
    ]),
  );

  return locked
    .filter(({ name, version }) => tooYoung(index.get(name).get(version), now))
    .map((crate) => ({
      ...crate,
      pubtime: index.get(crate.name).get(crate.version),
    }));
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const lockfiles = execFileSync("git", ["ls-files", "*Cargo.lock"], {
    encoding: "utf8",
  })
    .split("\n")
    .filter(Boolean);
  const young = await check(lockfiles);

  for (const { path, name, version, pubtime } of young)
    console.error(
      `${path}: ${name} ${version} was published ${pubtime}, less than 7 days ago`,
    );

  if (young.length) process.exit(1);
  console.log(
    `Checked ${lockfiles.length} Cargo.lock files: every crates.io version is at least 7 days old.`,
  );
}
