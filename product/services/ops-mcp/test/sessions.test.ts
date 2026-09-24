import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, expect, it } from "vitest";
import { createSessions, type Session } from "../src/sessions.js";

const directories: string[] = [];
const storage = () => {
  const directory = mkdtempSync(join(tmpdir(), "ops-session-test-"));
  directories.push(directory);
  return join(directory, "sessions.json");
};
afterEach(() => {
  for (const directory of directories.splice(0))
    rmSync(directory, { recursive: true, force: true });
});
const session: Session = {
  client: "client",
  identity: { subject: "staff", email: "staff@gradiated.com" },
  expires: 2000,
  accessExpires: 1000,
  accessHash: "access-hash",
  refreshHash: "refresh-hash",
  usedRefreshHashes: [],
};

it("persists pruning and uses owner-only permissions", () => {
  const path = storage();
  const store = createSessions("test-key", path);
  store.put("expired", session);
  store.put("active", { ...session, expires: 3000 });
  expect(statSync(path).mode & 0o777).toBe(0o600);
  store.prune(2000);
  const restarted = createSessions("test-key", path);
  expect(restarted.get("expired")).toBeUndefined();
  expect(restarted.get("active")).toEqual({ ...session, expires: 3000 });
});

it("fails closed after a write error and retains the previously committed state", () => {
  const path = storage();
  const store = createSessions("test-key", path);
  store.put("one", session);
  const before = readFileSync(path, "utf8");
  mkdirSync(`${path}.tmp`);
  expect(() => store.remove("one")).toThrow("storage unavailable");
  expect(() => store.get("one")).toThrow("storage unavailable");
  expect(readFileSync(path, "utf8")).toBe(before);
});

it("refuses corrupt state rather than silently starting an empty store", () => {
  const path = storage();
  writeFileSync(path, '{"version":1,"sessions":"corrupt"}');
  expect(() => createSessions("test-key", path)).toThrow();
});
