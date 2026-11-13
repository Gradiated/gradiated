import { z } from "zod";

const API = "https://api.runpod.io/v2";
const REQUEST_TIMEOUT_MS = 30_000;

export const runPodSchema = z.object({
  id: z.string(),
  gpuCount: z.number().int().nonnegative(),
  vcpuCount: z.number().positive(),
  desiredStatus: z.string().optional(),
  imageName: z.string().optional(),
  // When the container last started. A network outage leaves it alone; a
  // restart, re-image or move to another machine resets it.
  lastStartedAt: z.string().nullish(),
  env: z.record(z.string(), z.string()).nullish(),
  // A RunPod volume survives a re-image; the container disk does not.
  volumeInGb: z.number().nonnegative().nullish(),
  hasAttachedVolumes: z.boolean().optional(),
  machine: z.object({
    dataCenterId: z.string().nullish(),
    gpuTypeId: z.string().nullish(),
  }),
});

const v2PodSchema = z
  .object({
    id: z.string(),
    status: z.string(),
    image: z.string(),
    startedAt: z.string().nullable(),
    env: z.record(z.string(), z.string()),
    dataCenterId: z.string().nullable(),
    gpu: z
      .object({
        id: z.string(),
        count: z.number().int().positive().default(1),
        vcpuCount: z.number().positive(),
      })
      .optional(),
    cpu: z.object({ vcpuCount: z.number().positive() }).optional(),
    mounts: z.object({
      persistent: z.object({ size: z.number().nonnegative() }).optional(),
      network: z.array(z.object({ volumeId: z.string() })).optional(),
      global: z.array(z.object({ volumeId: z.string() })).optional(),
    }),
  })
  .refine((pod) => Boolean(pod.gpu) !== Boolean(pod.cpu), {
    message: "Expected GPU or CPU configuration",
  })
  .transform((pod) =>
    runPodSchema.parse({
      id: pod.id,
      desiredStatus: pod.status,
      imageName: pod.image,
      lastStartedAt: pod.startedAt,
      env: pod.env,
      gpuCount: pod.gpu?.count ?? 0,
      vcpuCount: pod.gpu?.vcpuCount ?? pod.cpu!.vcpuCount,
      volumeInGb: pod.mounts.persistent?.size ?? 0,
      hasAttachedVolumes: Boolean(
        pod.mounts.network?.length || pod.mounts.global?.length,
      ),
      machine: { dataCenterId: pod.dataCenterId, gpuTypeId: pod.gpu?.id },
    }),
  );

const identitySchema = z.object({
  data: z.object({
    pod: z.object({ consumerUserId: z.string(), machineId: z.string() }),
  }),
});

export type RunPod = z.infer<typeof runPodSchema>;

export class RunPodError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export const createRunPodClient = ({
  apiKey,
  fetch: request = fetch,
  userAgent,
}: {
  readonly apiKey: string;
  readonly fetch?: typeof fetch;
  readonly userAgent: string;
}) => {
  const call = async (
    method: string,
    path: string,
    body?: unknown,
    base = API,
  ) => {
    const response = await request(`${base}${path}`, {
      method,
      headers: {
        authorization: `Bearer ${apiKey}`,
        "content-type": "application/json",
        // RunPod's edge rejects requests without a client identity.
        "user-agent": userAgent,
      },
      body: body === undefined ? null : JSON.stringify(body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    const text = await response.text();
    if (!response.ok)
      throw new RunPodError(
        response.status,
        `RunPod ${method} ${path} failed: ${response.status}`,
      );
    return text === "" ? null : (JSON.parse(text) as unknown);
  };
  const id = (podId: string) =>
    encodeURIComponent(
      z
        .string()
        .regex(/^[a-z0-9]{1,40}$/)
        .parse(podId),
    );

  return {
    pod: async (podId: string) =>
      v2PodSchema.parse(await call("GET", `/pods/${id(podId)}`)),
    // REST v2 omits account and physical machine identity; enrollment needs both.
    identity: async (podId: string) => {
      const result = await call(
        "POST",
        "/graphql",
        {
          query:
            "query($input: PodFilter!) { pod(input: $input) { consumerUserId machineId } }",
          variables: { input: { podId: id(podId) } },
        },
        "https://api.runpod.io",
      );
      if (
        z.object({ errors: z.array(z.unknown()).optional() }).parse(result)
          .errors?.length
      )
        throw new Error("RunPod identity lookup failed");

      return identitySchema.parse(result).data.pod;
    },
    // Any update resets the pod and wipes its container filesystem.
    update: async (
      podId: string,
      body: { imageName: string; ports: string[]; env: Record<string, string> },
    ) => {
      const { imageName, ...settings } = body;
      await call("PATCH", `/pods/${id(podId)}`, {
        ...settings,
        image: imageName,
      });
    },
    start: async (podId: string) => {
      await call("POST", `/pods/${id(podId)}/action`, { action: "start" });
    },
  };
};

export type RunPodClient = ReturnType<typeof createRunPodClient>;
