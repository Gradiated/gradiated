import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

export const isRuntimeOwnedJob = (job) =>
  Boolean(job.Meta?.gradiated_buffer_for) ||
  (job.Type === "batch" &&
    /^training-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-[1-9]\d*$/.test(
      job.ID,
    ));

export const assertCanStopJob = (job) => {
  if (
    isRuntimeOwnedJob(job) ||
    (job.Meta?.gradiated_model_id &&
      (job.TaskGroups ?? []).some((group) => group.Count > 0))
  )
    throw new Error(
      `${job.ID}: routine cleanup cannot stop a model, training job or controller-owned buffer`,
    );
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    const job = JSON.parse(readFileSync(0, "utf8"));
    if (process.argv[2] === "--runtime-owned") {
      process.exitCode = isRuntimeOwnedJob(job) ? 0 : 1;
    } else {
      assertCanStopJob(job);
    }
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
