import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import { catalog } from "../images/catalog.mjs";
import { bundles } from "./release.mjs";

const workflow = readFileSync(".github/workflows/model-deployment.yml", "utf8");
const block = workflow.match(/    paths:\n((?:      - .+\n)+)/)?.[1];
assert.ok(block, "Model publication must declare push paths");
const patterns = block
  .trim()
  .split("\n")
  .map((line) => line.trim().slice(2));
const matches = (path) =>
  patterns.some((pattern) =>
    pattern.endsWith("/**")
      ? path.startsWith(pattern.slice(0, -2))
      : path === pattern,
  );

test("every base-image input triggers model publication", () => {
  for (const path of catalog["gpu-base"].paths)
    assert.ok(matches(path.endsWith("/") ? `${path}input.cpp` : path), path);
});

test("every bundle input triggers model publication", () => {
  for (const path of Object.values(bundles).flat())
    assert.ok(
      matches(statSync(path).isDirectory() ? `${path}/input` : path),
      path,
    );
});
