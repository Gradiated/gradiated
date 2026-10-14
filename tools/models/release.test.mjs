import test from "node:test";
import assert from "node:assert/strict";
import { inputDigest, manifest } from "./release.mjs";

const baseImage = `registry/base@sha256:${"a".repeat(64)}`;
test("bundle identity changes with base digest or runtime input", () => {
  const original = inputDigest(baseImage, "tree-a");
  assert.notEqual(original, inputDigest(baseImage, "tree-b"));
  assert.notEqual(
    original,
    inputDigest(baseImage.replace(/a{64}/, "b".repeat(64)), "tree-a"),
  );
  assert.equal(original, inputDigest(baseImage, "tree-a"));
});
test("mutable base references are rejected", () => {
  assert.throws(() => inputDigest("registry/base:latest", "tree"), /pinned/);
});
test("release binds the source, base and content-addressed private bundle", () => {
  const record = manifest({
    source: "c".repeat(40),
    baseImage,
    baseId: "base-v1",
    digest: "d".repeat(64),
    bucket: "test-artifacts",
  });
  assert.equal(record.baseImage, baseImage);
  assert.equal(record.sha256, "d".repeat(64));
  assert.equal(
    record.url,
    `s3::https://test-artifacts.s3.us-east-1.amazonaws.com/bundles/sha256/${record.sha256}.tar.gz`,
  );
});

test("release records distinguish host bundles from model runtimes", () => {
  const record = manifest({bundle:"host", source:"c".repeat(40), baseImage, baseId:"base-v1", digest:"d".repeat(64), bucket:"test-artifacts"});
  assert.equal(record.bundle, "host");
  assert.equal(record.bootstrapVersion, 1);
  assert.throws(() => manifest({bundle:"unknown", source:"c".repeat(40), baseImage, baseId:"base-v1", digest:"d".repeat(64), bucket:"test-artifacts"}), /Unknown bundle/);
});
