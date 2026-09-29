import { Agent, request } from "node:https";

import { ModelDeploymentReleaseSchema } from "@gradiated/contracts";
import type { NomadAllocation } from "@gradiated/control";
import { z } from "zod";
import {
  cliProfile,
  expiryTimestamp,
  issueCertificate,
  kmsSigner,
  renewingCertificate,
  type CertificateSigner,
} from "@gradiated/nomad-pki";

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
    DeploymentStatus: z.object({ Canary: z.boolean().optional() }).nullish(),
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

      const gated = versions.Versions.some(
        (version) => version.Meta?.gradiated_sdk_verification === "true",
      );
      const deployments = gated
        ? z
            .array(
              z.object({ JobVersion: z.number().int(), Status: z.string() }),
            )
            .parse((await get(`${path}/deployments`)) ?? [])
        : [];
      const unverified = new Set(
        deployments
          .filter((deployment) => deployment.Status !== "successful")
          .map((deployment) => deployment.JobVersion),
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
              ...(versionMeta?.gradiated_sdk_verification === "true" &&
              (allocation.DeploymentStatus?.Canary ||
                unverified.has(allocation.JobVersion))
                ? { verificationPending: true }
                : {}),
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
    if ((error as { code?: unknown }).code === "404") return true;
    throw error;
  }
};

export const createNomadGet = (
  nomad: NomadEnvironment,
  options: {
    signer?: CertificateSigner;
    onCertificate?: (expires: number) => void;
  } = {},
): NomadGet => {
  const signingKey = nomad.NOMAD_CA_KMS_KEY;
  const certificate = signingKey
    ? renewingCertificate(async () => {
        const issued = await issueCertificate(
          nomad.NOMAD_CA_PEM,
          options.signer ?? kmsSigner(signingKey),
          cliProfile,
        );
        options.onCertificate?.(expiryTimestamp(issued.certificate));
        return issued;
      })
    : undefined;
  const agent = new Agent({
    keepAlive: true,
    ca: nomad.NOMAD_CA_PEM,
    timeout: 30_000,
    servername: SERVER_NAME,
  });

  return async (path) => {
    const issued = await certificate?.get();
    return new Promise((resolve, reject) => {
      const outgoing = request(
        new URL(path, nomad.NOMAD_ADDR),
        {
          agent,
          cert: issued?.certificate ?? nomad.NOMAD_CLIENT_CERT_PEM,
          key: issued?.privateKey ?? nomad.NOMAD_CLIENT_KEY_PEM,
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
};
