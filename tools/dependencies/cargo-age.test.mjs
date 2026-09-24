import test from "node:test";
import assert from "node:assert/strict";
import {
  indexPath,
  lockedCrates,
  pubtimes,
  tooYoung,
  MIN_AGE_MS,
} from "./cargo-age.mjs";

test("index paths follow the crates.io sparse index layout", () => {
  assert.equal(indexPath("a"), "1/a");
  assert.equal(indexPath("ab"), "2/ab");
  assert.equal(indexPath("abc"), "3/a/abc");
  assert.equal(indexPath("Serde_JSON"), "se/rd/serde_json");
});

test("only crates.io packages are checked", () => {
  const lockfile = `version = 4

[[package]]
name = "serde"
version = "1.0.219"
source = "registry+https://github.com/rust-lang/crates.io-index"
checksum = "abc"

[[package]]
name = "gradiated-proxy"
version = "0.1.0"

[[package]]
name = "forked"
version = "0.2.0"
source = "git+https://github.com/example/forked#abc"
`;

  assert.deepEqual(lockedCrates(lockfile), [
    {
      name: "serde",
      version: "1.0.219",
      source: "registry+https://github.com/rust-lang/crates.io-index",
    },
  ]);
});

test("a version is too young only within the minimum age", () => {
  const now = Date.parse("2026-09-24T12:00:00Z");

  assert.equal(tooYoung("2026-09-24T00:00:00Z", now), true);
  assert.equal(
    tooYoung(new Date(now - MIN_AGE_MS + 1).toISOString(), now),
    true,
  );
  assert.equal(tooYoung(new Date(now - MIN_AGE_MS).toISOString(), now), false);
  assert.equal(tooYoung(undefined, now), false);
});

test("index lines map versions to their publish times", () => {
  const body = [
    JSON.stringify({ name: "zstd", vers: "0.13.3" }),
    JSON.stringify({
      name: "zstd",
      vers: "0.14.0",
      pubtime: "2026-09-04T10:00:00Z",
    }),
    "",
  ].join("\n");

  const times = pubtimes(body);

  assert.equal(times.get("0.13.3"), undefined);
  assert.equal(times.get("0.14.0"), "2026-09-04T10:00:00Z");
});
