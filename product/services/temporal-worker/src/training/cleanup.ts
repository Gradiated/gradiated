import { z } from "zod";
import type { NomadRequest } from "@gradiated/nomad-pki";
import type { TrainingEngine } from "@gradiated/control";
import { trainingWorkflowId } from "@gradiated/temporal";

const jobsSchema = z.array(
  z.object({
    ID: z.string(),
    Stop: z.boolean(),
    Status: z.string(),
  }),
);

export const stopClosedTrainingJobs = async (input: {
  request: NomadRequest;
  engine: Pick<TrainingEngine, "status">;
  readRun: (
    id: string,
  ) => Promise<{ taskId: string; workflowId: string | null } | undefined>;
}) => {
  const jobs = jobsSchema.parse(
    (await input.request("/v1/jobs?prefix=training-")) ?? [],
  );

  for (const job of jobs) {
    if (job.Stop || !["pending", "running"].includes(job.Status)) continue;

    const match = /^training-([0-9a-f-]{36})-[1-9]\d*$/.exec(job.ID);
    const id = z.uuid().safeParse(match?.[1]);
    if (!id.success) continue;

    try {
      const run = await input.readRun(id.data);
      if (!run) continue;

      const status = await input.engine.status(
        run.workflowId ?? trainingWorkflowId(run.taskId),
        id.data,
      );
      if (status === "running") continue;

      await input.request(
        `/v1/job/${encodeURIComponent(job.ID)}?purge=false`,
        "DELETE",
      );
    } catch {
      console.warn("Could not clean up training job.", { jobId: job.ID });
    }
  }
};
