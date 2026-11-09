import { z } from "zod";

const API = "https://rest.runpod.io/v1";
const REQUEST_TIMEOUT_MS = 30_000;

export const runPodSchema = z.object({
  id: z.string(),
  consumerUserId: z.string(),
  machineId: z.string(),
  gpuCount: z.number().int().nonnegative(),
  vcpuCount: z.number().int().positive(),
  desiredStatus: z.string().optional(),
  imageName: z.string().optional(),
  // When the container last started. A network outage leaves it alone; a
  // restart, re-image or move to another machine resets it.
  lastStartedAt: z.string().nullish(),
  env: z.record(z.string(), z.string()).nullish(),
  // A RunPod volume survives a re-image; the container disk does not.
  volumeInGb: z.number().nonnegative().nullish(),
  machine: z.object({
    dataCenterId: z.string().nullish(),
    gpuTypeId: z.string().nullish(),
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
  const call = async (method: string, path: string, body?: unknown) => {
    const response = await request(`${API}${path}`, {
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
      runPodSchema.parse(
        await call("GET", `/pods/${id(podId)}?includeMachine=true`),
      ),
    // Any update resets the pod and wipes its container filesystem.
    update: async (podId: string, body: Record<string, unknown>) => {
      await call("PATCH", `/pods/${id(podId)}`, body);
    },
    start: async (podId: string) => {
      await call("POST", `/pods/${id(podId)}/start`);
    },
  };
};

export type RunPodClient = ReturnType<typeof createRunPodClient>;
