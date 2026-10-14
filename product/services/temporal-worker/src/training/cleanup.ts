import { z } from "zod";
import type { TrainingEngine } from "@gradiated/control";
import { trainingWorkflowId } from "@gradiated/temporal";
import type { KubernetesRequest } from "./kubernetes-host.js";

const jobsPath = "/apis/batch/v1/namespaces/gpu-inference/jobs";
const jobsSchema = z.object({
  items: z.array(
    z.object({
      metadata: z.object({
        name: z.string(),
        uid: z.uuid(),
        deletionTimestamp: z.string().optional(),
        labels: z.record(z.string(), z.string()).default({}),
      }),
      status: z
        .object({
          conditions: z
            .array(z.object({ type: z.string(), status: z.string() }))
            .default([]),
        })
        .default({ conditions: [] }),
    }),
  ),
  metadata: z.object({ continue: z.string().optional() }).default({}),
});
export const stopClosedTrainingJobs = async (input: {
  request: KubernetesRequest;
  engine: Pick<TrainingEngine, "status">;
  readRun: (
    id: string,
  ) => Promise<{ taskId: string; workflowId: string | null } | undefined>;
}) => {
  let cursor = "";
  do {
    const page = jobsSchema.parse(
      await input.request(
        `${jobsPath}?labelSelector=gradiated.com%2Ftraining-run&limit=250${cursor ? `&continue=${encodeURIComponent(cursor)}` : ""}`,
      ),
    );
    cursor = page.metadata.continue ?? "";
    for (const job of page.items) {
      if (
        job.metadata.deletionTimestamp ||
        job.status.conditions.some(
          (c) => ["Complete", "Failed"].includes(c.type) && c.status === "True",
        )
      )
        continue;
      const match = /^training-([0-9a-f-]{36})-[1-9]\d*$/.exec(
        job.metadata.name,
      );
      const id = z.uuid().safeParse(match?.[1]);
      if (
        !id.success ||
        job.metadata.labels["gradiated.com/training-run"] !== id.data
      )
        continue;
      try {
        const run = await input.readRun(id.data);
        if (!run) continue;
        const status = await input.engine.status(
          run.workflowId ?? trainingWorkflowId(run.taskId),
          id.data,
        );
        if (status === "running") continue;
        await input.request(`${jobsPath}/${job.metadata.name}`, "DELETE", {
          apiVersion: "v1",
          kind: "DeleteOptions",
          propagationPolicy: "Foreground",
          preconditions: { uid: job.metadata.uid },
        });
      } catch {
        console.warn("Could not clean up training job.", {
          jobId: job.metadata.name,
        });
      }
    }
  } while (cursor);
};
