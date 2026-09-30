import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

export const assertCanStopJob = (job) => {
  if (
    job.Meta?.gradiated_buffer_for ||
    (job.Meta?.gradiated_model_id &&
      (job.TaskGroups ?? []).some((group) => group.Count > 0))
  )
    throw new Error(
      `${job.ID}: routine cleanup cannot stop a model or controller-owned buffer`,
    );
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    assertCanStopJob(JSON.parse(readFileSync(0, "utf8")));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
