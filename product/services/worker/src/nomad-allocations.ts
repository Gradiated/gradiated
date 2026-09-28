import { Agent, request } from "node:https";

import { ModelDeploymentReleaseSchema } from "@gradiated/contracts";
import type { NomadAllocation } from "@gradiated/control";
import { z } from "zod";

import type { NomadEnvironment } from "./environment.js";

export type NomadGet = (path: string) => Promise<unknown>;

const REQUEST_TIMEOUT_MS = 10_000;
const SERVER_NAME = "server.global.nomad";

const meta = z.record(z.string(), z.string()).nullish();
const jobsSchema = z.array(z.object({ ID: z.string(), Meta: meta }));
const allocationsSchema = z.array(
  z.object({
    ID: z.string(),
    NodeID: z.string(),
    ClientStatus: z.string(),
    DesiredStatus: z.string(),
    JobVersion: z.number().int(),
  }),
);
const versionsSchema = z.object({
  Versions: z.array(z.object({ Version: z.number().int(), Meta: meta })),
});

const parseRelease = (value: string | undefined) => {
  try {
    return ModelDeploymentReleaseSchema.safeParse(JSON.parse(value ?? ""));
  } catch {
    return { success: false as const };
  }
};

// Model jobs carry meta.gradiated_model_id and a JSON meta.gradiated_release. The
// release comes from each allocation's own job version so a rollout stays correct.
export const readModelAllocations = async (
  get: NomadGet,
  onSkipped: (allocationId: string, modelId: string) => void,
): Promise<NomadAllocation[]> => {
  const jobs = jobsSchema
    .parse(await get("/v1/jobs?meta=true"))
    .filter((job) => job.Meta?.gradiated_model_id);

  const perJob = await Promise.all(
    jobs.map(async (job) => {
      const path = `/v1/job/${encodeURIComponent(job.ID)}`;
      const [allocations, versions] = await Promise.all([
        get(`${path}/allocations`).then((body) =>
          allocationsSchema.parse(body),
        ),
        get(`${path}/versions`).then((body) => versionsSchema.parse(body)),
      ]);
      const metaByVersion = new Map(
        versions.Versions.map((version) => [version.Version, version.Meta]),
      );

      return allocations
        .filter((allocation) => allocation.ClientStatus === "running")
        .flatMap((allocation) => {
          const versionMeta = metaByVersion.get(allocation.JobVersion);
          const modelId = versionMeta?.gradiated_model_id;
          const release = parseRelease(versionMeta?.gradiated_release);
          if (!modelId || !release.success) {
            onSkipped(allocation.ID, job.Meta?.gradiated_model_id ?? "");
            return [];
          }

          return [
            {
              allocationId: allocation.ID,
              nodeId: allocation.NodeID,
              modelId,
              release: release.data,
              draining: allocation.DesiredStatus !== "run",
            },
          ];
        });
    }),
  );

  return perJob.flat();
};

const TERMINAL_STATUSES = new Set(["complete", "failed", "lost"]);
const allocationSchema = z.object({ ClientStatus: z.string() });

export const allocationIsGone = async (
  get: NomadGet,
  allocationId: string,
): Promise<boolean> => {
  try {
    const allocation = allocationSchema.parse(
      await get(`/v1/allocation/${encodeURIComponent(allocationId)}`),
    );
    return TERMINAL_STATUSES.has(allocation.ClientStatus);
  } catch (error) {
    // A row whose id Nomad does not know may not be an allocation at all, such as
    // a deployment configured by hand, so only a terminal allocation removes one.
    if ((error as { code?: unknown }).code === "404") return false;
    throw error;
  }
};

export const createNomadGet = (nomad: NomadEnvironment): NomadGet => {
  const agent = new Agent({
    keepAlive: true,
    ca: nomad.NOMAD_CA_PEM,
    cert: nomad.NOMAD_CLIENT_CERT_PEM,
    key: nomad.NOMAD_CLIENT_KEY_PEM,
    servername: SERVER_NAME,
  });

  return (path) =>
    new Promise((resolve, reject) => {
      const outgoing = request(
        new URL(path, nomad.NOMAD_ADDR),
        {
          agent,
          headers: { "x-nomad-token": nomad.NOMAD_TOKEN },
          signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
        },
        (response) => {
          let body = "";
          response.setEncoding("utf8");
          response.on("data", (chunk: string) => (body += chunk));
          response.on("close", () => {
            if (!response.complete) {
              reject(
                Object.assign(new Error(`Nomad ${path} ended early`), {
                  code: "ECONNRESET",
                }),
              );
            }
          });
          response.on("end", () => {
            if (response.statusCode !== 200) {
              reject(
                Object.assign(
                  new Error(`Nomad ${path} returned ${response.statusCode}`),
                  { code: String(response.statusCode) },
                ),
              );
              return;
            }
            try {
              resolve(JSON.parse(body));
            } catch (error) {
              reject(error);
            }
          });
        },
      );
      // The logger never prints messages, so a timeout needs a code to be told apart.
      outgoing.on("error", (error) =>
        reject(
          error.name === "AbortError"
            ? Object.assign(error, { code: "ETIMEDOUT" })
            : error,
        ),
      );
      outgoing.end();
    });
};
