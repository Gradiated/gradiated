import assert from "node:assert/strict";
import test from "node:test";
import { assertCanStopJob } from "./cleanup-jobs.mjs";

test("a controller-owned buffer cannot be removed by routine cleanup", () => {
  assert.throws(
    () =>
      assertCanStopJob({
        ID: "kev-9b-buffer",
        Meta: { gradiated_buffer_for: "kev-9b" },
        TaskGroups: [{ Count: 1 }],
      }),
    /controller-owned buffer/,
  );
});

test("missing vars cannot retire an active serving model", () => {
  assert.throws(
    () =>
      assertCanStopJob({
        ID: "kev-9b",
        Meta: { gradiated_model_id: "jaredpalmer/kev-9b" },
        TaskGroups: [{ Count: 2 }],
      }),
    /routine cleanup cannot stop/,
  );
});

test("ordinary jobs and disabled models remain eligible for cleanup", () => {
  assert.doesNotThrow(() =>
    assertCanStopJob({ ID: "old-job", TaskGroups: [{ Count: 1 }] }),
  );
  assert.doesNotThrow(() =>
    assertCanStopJob({
      ID: "old-model",
      Meta: { gradiated_model_id: "old" },
      TaskGroups: [{ Count: 0 }],
    }),
  );
});
