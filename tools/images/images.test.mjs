import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { catalog } from "./catalog.mjs";
import { fingerprint, matches, plan } from "./images.mjs";
const entry = (path, meta = "100644 blob aaa") => ({ path, meta });

test("every local base-image COPY source participates in its identity", () => {
  const image = catalog["nomad-base"];
  const dockerfile = readFileSync(image.dockerfile, "utf8");
  for (const line of dockerfile
    .split("\n")
    .filter((line) => /^COPY\s/.test(line))) {
    const args = line.trim().split(/\s+/).slice(1);
    if (args.some((arg) => arg.startsWith("--from="))) continue;
    assert.ok(
      !line.includes("[") && !line.endsWith("\\"),
      "Extend COPY coverage for new Dockerfile syntax",
    );
    for (const source of args
      .filter((arg) => !arg.startsWith("--"))
      .slice(0, -1)) {
      const path = `${image.context}/${source}`;
      assert.ok(matches(path, image.paths), `Missing image input: ${path}`);
    }
  }
});
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
test("Nomad configuration changes do not rebuild the application image", () => {
  const base = [entry("product/Dockerfile")];
  assert.equal(
    fingerprint("product", base),
    fingerprint("product", [
      ...base,
      entry("infra/environments/prod/us-east-1/kubernetes/nomad/servers.yaml"),
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

test("plans all enabled images against the actual repository tree", () => {
  const revision = execFileSync("git", ["rev-parse", "HEAD"], {
    encoding: "utf8",
  }).trim();
  const names = ["product", "gateway", "deepseek-v4-1-flash"];
  const result = plan(names, revision);
  assert.deepEqual(
    result.include.map((image) => image.name),
    names,
  );
  for (const image of result.include)
    assert.match(image.tag, /-inputs-[0-9a-f]{64}$/);
  assert.deepEqual(
    plan(["deepseek-v4-1-flash"], revision).include[0],
    result.include[2],
  );
});

test("Nomad serving bootstrap and proxy edits invalidate the base image", () => {
  for (const path of [
    "product/inference/images/nomad-base/configure-serving.sh",
    "product/inference/images/nomad-base/runtime-proxy.conf.template",
    "product/inference/nomad/client.hcl",
  ]) {
    assert.notEqual(
      fingerprint("nomad-base", [entry(path)]),
      fingerprint("nomad-base", [entry(path, "100644 blob bbb")]),
    );
  }
});
