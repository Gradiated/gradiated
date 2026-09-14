import test from "node:test";
import assert from "node:assert/strict";
import { updateRelay } from "./record-relay.mjs";
const images = {
  "nomad-relay": {
    digest: `sha256:${"a".repeat(64)}`,
    repository: "gradiated/prod/inference",
  },
};
const account = "123456789012";
test("pins only the relay and supports repeat releases", () => {
  const before = "replicas: 3\n  image: nomad-relay:deployment-pending\n";
  const after = updateRelay(before, images, account);
  assert.ok(after.includes(`@${images["nomad-relay"].digest}`));
  assert.ok(after.startsWith("replicas: 3\n"));
  assert.equal(updateRelay(after, images, account), after);
});
test("rejects invalid digests and missing or ambiguous targets", () => {
  assert.throws(() =>
    updateRelay(
      "  image: nomad-relay:deployment-pending\n",
      { "nomad-relay": { ...images["nomad-relay"], digest: "latest" } },
      account,
    ),
  );
  assert.throws(() => updateRelay("  image: unrelated\n", images, account));
  assert.throws(() =>
    updateRelay(
      "  image: nomad-relay:deployment-pending\n".repeat(2),
      images,
      account,
    ),
  );
});
