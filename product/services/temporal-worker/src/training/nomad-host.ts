import { setTimeout as delay } from "node:timers/promises";
import { z } from "zod";
import type { NomadRequest } from "@gradiated/nomad-pki";

const allocation = z.object({
  ID: z.guid(),
  NodeID: z.guid(),
  ClientStatus: z.string(),
});
export type TrainingHost = { allocationId: string; jobId: string; url: string };
export type TrainingNode = { nodeId: string; podId: string };
export type TrainingHostConfig = {
  bundleUrl: string;
  bundleSha256: string;
  baseId: string;
  gpuType: string;
  nodePool?: string | undefined;
  recipe?: Record<string, unknown> | undefined;
};

export const trainingHostJob = (
  runId: string,
  ordinal: number,
  nodes: TrainingNode[],
  config: TrainingHostConfig,
) => {
  z.uuid().parse(runId);
  z.number().int().min(1).parse(ordinal);
  z.array(
    z.object({ nodeId: z.guid(), podId: z.string().regex(/^[a-z0-9]+$/) }),
  )
    .min(1)
    .max(4)
    .parse(nodes);
  z.string()
    .regex(/^[0-9a-f]{64}$/)
    .parse(config.bundleSha256);
  const gpuCount = z
    .number()
    .int()
    .min(1)
    .max(8)
    .parse(config.recipe?.gpu_count ?? 1);
  const id = `training-${runId}-${ordinal}`;
  return {
    ID: id,
    Name: id,
    Type: "batch",
    NodePool: config.nodePool ?? "default",
    Datacenters: ["dc1"],
    Constraints: [
      {
        LTarget: "${node.unique.id}",
        Operand: "regexp",
        RTarget: `^(${nodes.map((node) => node.nodeId).join("|")})$`,
      },
      {
        LTarget: "${meta.runtime_base_id}",
        Operand: "=",
        RTarget: config.baseId,
      },
      {
        LTarget: "${meta.serving_ingress}",
        Operand: "=",
        RTarget: "host-proxy",
      },
    ],
    TaskGroups: [
      {
        Name: "trainer",
        Count: 1,
        RestartPolicy: {
          Attempts: 0,
          Mode: "fail",
          Interval: 60_000_000_000,
          Delay: 0,
        },
        ReschedulePolicy: { Attempts: 0, Unlimited: false, Interval: 0 },
        Disconnect: { Replace: false, StopOnClientAfter: 60_000_000_000 },
        EphemeralDisk: { SizeMB: 12000 },
        Networks: [
          {
            Mode: "host",
            DynamicPorts: [{ Label: "runtime", HostNetwork: "loopback" }],
          },
        ],
        Tasks: [
          {
            Name: "download-runtime",
            Driver: "raw_exec",
            User: "downloader",
            Lifecycle: { Hook: "prestart", Sidecar: false },
            Config: {
              command: "/usr/bin/setpriv",
              args: [
                "--inh-caps=-all",
                "--ambient-caps=-all",
                "--no-new-privs",
                "/bin/bash",
                "/opt/gradiated/bin/fetch-runtime",
                config.bundleUrl,
                config.bundleSha256,
                "${NOMAD_ALLOC_DIR}/runtime",
              ],
            },
            Resources: { CPU: 1000, MemoryMB: 1024 },
          },
          {
            Name: "trainer",
            Driver: "raw_exec",
            User: "runtime",
            KillSignal: "SIGTERM",
            KillTimeout: 30_000_000_000,
            Config: {
              command: "/usr/bin/setpriv",
              args: [
                "--inh-caps=-all",
                "--ambient-caps=-all",
                "--no-new-privs",
                "/bin/bash",
                "${NOMAD_ALLOC_DIR}/runtime/claim-gpus.sh",
                "${NOMAD_ALLOC_DIR}/runtime",
              ],
            },
            Env: {
              HOME: "/home/runtime",
              GRADIATED_RUNTIME_ROOT: "${NOMAD_ALLOC_DIR}/runtime",
              TRAINER_IMAGE_DIGEST: config.bundleSha256,
              ...(config.recipe
                ? { TRAINING_RECIPE_JSON: JSON.stringify(config.recipe) }
                : {}),
            },
            Resources: {
              CPU: 4000 * gpuCount,
              MemoryMB: 64000 * gpuCount,
              Devices: [
                {
                  Name: "nvidia/gpu",
                  Count: gpuCount,
                  Constraints: [
                    {
                      LTarget: "${device.model}",
                      Operand: "regexp",
                      RTarget: config.gpuType,
                    },
                  ],
                },
              ],
            },
            Services: [
              {
                Name: "gradiated-runtime",
                Provider: "nomad",
                Address: "127.0.0.1",
                PortLabel: "runtime",
                Checks: [
                  {
                    Name: "trainer-ready",
                    Type: "http",
                    Path: "/health",
                    Interval: 10_000_000_000,
                    Timeout: 2_000_000_000,
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  };
};

export const createTrainingHosts = (input: {
  request: NomadRequest;
  nodes: () => Promise<TrainingNode[]>;
  config: TrainingHostConfig;
  token: string;
  fetch?: typeof fetch;
  signal?: () => AbortSignal;
}) => {
  const request = input.request;
  const http = input.fetch ?? fetch;
  const allocations = async (jobId: string) =>
    z
      .array(allocation)
      .parse(
        (await request(
          `/v1/job/${encodeURIComponent(jobId)}/allocations?all=true`,
        )) ?? [],
      );
  const call = async (host: TrainingHost, path: string, command?: unknown) => {
    const signal = AbortSignal.any([
      AbortSignal.timeout(30_000),
      ...(input.signal ? [input.signal()] : []),
    ]);

    for (let attempt = 0; ; attempt++) {
      const response = await http(`${host.url}${path}`, {
        method: command === undefined ? "GET" : "POST",
        headers: {
          authorization: `Bearer ${input.token}`,
          "content-type": "application/json",
        },
        ...(command === undefined ? {} : { body: JSON.stringify(command) }),
        signal,
      });
      if (response.ok) return response.json() as Promise<unknown>;

      await response.body?.cancel();
      if (response.status < 500 || attempt === 2)
        throw new Error(`Trainer request failed (${response.status}).`);

      await delay(1000 * (attempt + 1), undefined, { signal });
    }
  };
  const renew = async (host: TrainingHost) => {
    const found = await allocations(host.jobId);
    const current = found.find((item) => item.ID === host.allocationId);
    if (current?.ClientStatus !== "running")
      throw new Error("Training reservation is no longer running.");

    z.object({ renewed: z.literal(true) }).parse(
      await call(host, "/reservation", { allocation_id: host.allocationId }),
    );
  };
  return {
    call,
    renew,
    async allocate(
      runId: string,
      ordinal: number,
      config = input.config,
    ): Promise<TrainingHost | null> {
      const nodes = await input.nodes();
      if (!nodes.length) return null;

      const job = trainingHostJob(runId, ordinal, nodes, config);
      try {
        await request(`/v1/job/${encodeURIComponent(job.ID)}`);
      } catch (error) {
        if ((error as { code?: string }).code !== "404") throw error;
        await request("/v1/jobs", "POST", { Job: job });
      }
      const found = await allocations(job.ID);
      if (
        found.some((item) =>
          ["failed", "lost", "complete"].includes(item.ClientStatus),
        )
      )
        throw new Error("Training host allocation failed.");
      const running = found.filter((item) => item.ClientStatus === "running");
      if (running.length > 1)
        throw new Error("Training host has duplicate allocations.");
      const current = running[0];
      if (current) {
        const node = nodes.find((node) => node.nodeId === current.NodeID);
        if (!node) throw new Error("Training allocation is outside its pool.");
        const host = {
          allocationId: current.ID,
          jobId: job.ID,
          url: `https://${node.podId}-8888.proxy.runpod.net/alloc/${current.ID}`,
        };
        try {
          await renew(host);
          return host;
        } catch {
          /* Readiness can lag allocation placement. */
        }
      }
      return null;
    },
    async release(runId: string) {
      z.uuid().parse(runId);
      const jobs = z
        .array(z.object({ ID: z.string() }))
        .parse((await request(`/v1/jobs?prefix=training-${runId}-`)) ?? []);
      const results = await Promise.allSettled(
        jobs.map(async (job) => {
          if (!job.ID.startsWith(`training-${runId}-`))
            throw new Error("Unexpected training job.");

          await request(
            `/v1/job/${encodeURIComponent(job.ID)}?purge=false`,
            "DELETE",
          );
        }),
      );
      const failed = results.find((result) => result.status === "rejected");
      if (failed?.status === "rejected") throw failed.reason;
    },
  };
};
