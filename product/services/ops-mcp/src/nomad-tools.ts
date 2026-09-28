import { z } from "zod";

import type { Backend } from "./backend.js";
import type { RegisterReadTool } from "./tools.js";

// List endpoints return stubs; full job and allocation objects embed the job
// specification, including its environment and templates.
const RESOURCES = {
  jobs: "/v1/jobs",
  allocations: "/v1/allocations",
  deployments: "/v1/deployments",
  evaluations: "/v1/evaluations",
  nodes: "/v1/nodes",
  node_pools: "/v1/node/pools",
} as const;

export const registerNomadTools = (
  register: RegisterReadTool,
  backend: Backend,
) => {
  register(
    "nomad",
    [
      "Read the Nomad cluster that runs the GPU inference fleet (GPU hosts are not EKS nodes).",
      "resource: jobs (status, type, version, submit time and per-task-group summary of running, failed and lost allocations); allocations (job, task group, node, client and desired status, times, and task states with restarts and recent events such as Terminated, Restarting, Driver Failure, with exit codes and messages); deployments (job version rollout status per task group); evaluations (scheduling decisions, blocked or failed placements); nodes (status, drain, eligibility, node pool, datacenter, class; include_resources adds capacity); node_pools.",
      'filter is a Nomad filter expression evaluated on the returned fields, for example ClientStatus == "failed", JobID contains "sglang", Status != "ready" or NodeName == "<name>". prefix matches the ID prefix. Times are Unix nanoseconds (CreateTime, ModifyTime, SubmitTime).',
      "Results come back as data plus next_token; a non-null next_token means more entries exist, so pass it back to read the next page. reverse returns newest first where Nomad supports it. Job specifications and environment are never returned.",
    ].join(" "),
    {
      resource: z.enum(Object.keys(RESOURCES) as [keyof typeof RESOURCES]),
      filter: z.string().min(1).max(1000).optional(),
      prefix: z
        .string()
        .regex(/^[A-Za-z0-9._-]+$/)
        .max(200)
        .optional(),
      namespace: z
        .string()
        .regex(/^[A-Za-z0-9_*-]+$/)
        .max(128)
        .default("*"),
      per_page: z.number().int().min(1).max(500).default(100),
      reverse: z.boolean().default(true),
      include_resources: z.boolean().default(false),
      next_token: z.string().min(1).max(512).optional(),
    },
    ({
      resource,
      filter,
      prefix,
      namespace,
      per_page,
      reverse,
      include_resources,
      next_token,
    }) =>
      backend("nomad", RESOURCES[resource], {
        namespace,
        per_page: String(per_page),
        reverse: String(reverse),
        ...(filter && { filter }),
        ...(prefix && { prefix }),
        ...(include_resources && { resources: "true" }),
        ...(next_token && { next_token }),
      }),
  );
};
