import assert from "node:assert/strict";
import test from "node:test";
import { assertCanStopJob, isRuntimeOwnedJob } from "./cleanup-jobs.mjs";

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

test("routine deployment preserves dynamically allocated training jobs", () => {
  const job = {
    ID: "training-01a0fe26-6c42-7705-b109-e83cb3ea090d-3",
    Type: "batch",
    TaskGroups: [{ Count: 1 }],
  };
  assert.equal(isRuntimeOwnedJob(job), true);
  assert.throws(() => assertCanStopJob(job), /training job/);
});

test("ordinary Git-owned jobs remain eligible even with a training prefix", () => {
  for (const job of [
    { ID: "training-service", Type: "service" },
    { ID: "training-01a0fe26-6c42-7705-b109-e83cb3ea090d-3", Type: "service" },
    { ID: "ordinary-batch", Type: "batch" },
    { ID: "training-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-1", Type: "batch" },
  ]) {
    assert.equal(isRuntimeOwnedJob(job), false);
    assert.doesNotThrow(() => assertCanStopJob(job));
  }
});
