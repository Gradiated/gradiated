import test from "node:test";
import assert from "node:assert/strict";
import { fingerprint } from "./images.mjs";
const entry = (path, meta = "100644 blob aaa") => ({ path, meta });
test("unrelated changes reuse the same image identity", () => {
  const base = [entry("product/services/gateway/Dockerfile")];
  assert.equal(
    fingerprint("gateway", base),
    fingerprint("gateway", [...base, entry("product/website/page.tsx")]),
  );
});
test("changed build contents and file modes produce a new identity", () => {
  assert.notEqual(
    fingerprint("gateway", [entry("product/services/gateway/Dockerfile")]),
    fingerprint("gateway", [
      entry("product/services/gateway/Dockerfile", "100755 blob aaa"),
    ]),
  );
  assert.notEqual(
    fingerprint("gateway", [entry("product/services/gateway/Dockerfile")]),
    fingerprint("gateway", [
      entry("product/services/gateway/Dockerfile", "100644 blob bbb"),
    ]),
  );
});
test("relay changes do not rebuild the application image", () => {
  const base = [entry("product/Dockerfile")];
  assert.equal(
    fingerprint("product", base),
    fingerprint("product", [
      ...base,
      entry("product/services/nomad-relay/src/main.rs"),
    ]),
  );
});
test("shared product packages invalidate the application image", () => {
  const base = [entry("product/Dockerfile")];
  assert.notEqual(
    fingerprint("product", base),
    fingerprint("product", [
      ...base,
      entry("product/packages/control/src/db/client.ts"),
    ]),
  );
});
test("unqualified GLM image and unknown image fail explicitly", () => {
  assert.throws(() => fingerprint("glm-5-3-flash", []), /qualified GLM/);
  assert.throws(() => fingerprint("typo", []), /Unknown image/);
});
