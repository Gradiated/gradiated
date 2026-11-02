import { spawn } from "node:child_process";
import { z } from "zod";
import { ModelDeploymentReleaseSchema } from "@gradiated/contracts";

const podSchema = z.object({
  metadata: z.object({
    uid: z.uuid(),
    name: z.string(),
    resourceVersion: z.string(),
    annotations: z.record(z.string(), z.string()).default({}),
    deletionTimestamp: z.string().optional(),
  }),
  spec: z.object({ nodeName: z.string().optional() }),
  status: z
    .object({
      conditions: z
        .array(z.object({ type: z.string(), status: z.string() }))
        .default([]),
      containerStatuses: z
        .array(z.object({ containerID: z.string().optional() }))
        .default([]),
    })
    .default({ conditions: [], containerStatuses: [] }),
});

export const qualificationCandidate = (value: unknown) => {
  const parsedPod = podSchema.safeParse(value);
  if (!parsedPod.success) return;

  const pod = parsedPod.data;
  const annotations = pod.metadata.annotations;
  const incarnation = pod.status.containerStatuses[0]?.containerID;
  if (
    pod.metadata.deletionTimestamp ||
    !pod.spec.nodeName?.startsWith("gpu-") ||
    !incarnation ||
    !pod.status.conditions.some(
      (c) => c.type === "RuntimeReady" && c.status === "True",
    ) ||
    (annotations["gradiated.com/qualified"] === "true" &&
      annotations["gradiated.com/qualified-runtime"] === incarnation) ||
    annotations["gradiated.com/qualification-error"] === incarnation
  )
    return;
  let release: unknown;
  try {
    release = JSON.parse(annotations["gradiated.com/release"] ?? "null");
  } catch {
    return;
  }
  const parsed = ModelDeploymentReleaseSchema.safeParse(release);
  const modelId =
    annotations["gradiated.com/serving-model-id"] ??
    annotations["gradiated.com/model-id"];
  if (!parsed.success || !modelId) return;
  return { pod, incarnation, modelId, release: parsed.data };
};

export const runSdkQualification = (
  input: unknown,
  signal: AbortSignal,
): Promise<void> =>
  new Promise((resolve, reject) => {
    const child = spawn(
      process.execPath,
      ["services/worker/dist/verify-model.js"],
      { signal, timeout: 8 * 60_000, stdio: ["pipe", "inherit", "inherit"] },
    );
    child.on("error", reject);
    child.stdin.on("error", reject);
    child.on("close", (code) =>
      code === 0
        ? resolve()
        : reject(new Error(`SDK qualification exited ${code}`)),
    );
    child.stdin.end(JSON.stringify(input));
  });

export const qualifyKubernetesPod = async (
  namespace: string,
  request: (path: string, method?: string, body?: unknown) => Promise<unknown>,
  availableModelIds: ReadonlySet<string>,
  verify: (input: unknown) => Promise<void>,
) => {
  const list = z.object({
    items: z.array(z.unknown()),
    metadata: z.object({ continue: z.string().optional() }),
  });
  const values: unknown[] = [];
  let cursor = "";
  do {
    const page = list.parse(
      await request(
        `/api/v1/namespaces/${namespace}/pods?limit=250${cursor ? `&continue=${encodeURIComponent(cursor)}` : ""}`,
      ),
    );
    values.push(...page.items);
    cursor = page.metadata.continue ?? "";
  } while (cursor);
  const candidate = values
    .map(qualificationCandidate)
    .find((c) => c !== undefined && availableModelIds.has(c.modelId));
  if (!candidate) return;
  const path = `/api/v1/namespaces/${namespace}/pods/${candidate.pod.metadata.name}`;
  let succeeded = true;
  try {
    await verify({
      stage: "canary",
      modelId: candidate.modelId,
      runtimeRevision: candidate.release.runtime_revision,
      ...(candidate.release.protocol
        ? { protocol: candidate.release.protocol }
        : {}),
      deploymentIds: [candidate.pod.metadata.uid],
      replicaRollout: true,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    succeeded = false;
  }
  const current = podSchema.parse(await request(path));
  if (
    current.metadata.uid !== candidate.pod.metadata.uid ||
    current.metadata.deletionTimestamp ||
    current.status.containerStatuses[0]?.containerID !== candidate.incarnation
  )
    return;
  const patch: unknown[] = [
    { op: "test", path: "/metadata/uid", value: current.metadata.uid },
    {
      op: "test",
      path: "/metadata/resourceVersion",
      value: current.metadata.resourceVersion,
    },
  ];
  if (succeeded)
    patch.push(
      {
        op: "add",
        path: "/metadata/annotations/gradiated.com~1qualified",
        value: "true",
      },
      {
        op: "add",
        path: "/metadata/annotations/gradiated.com~1qualified-runtime",
        value: candidate.incarnation,
      },
    );
  else
    patch.push({
      op: "add",
      path: "/metadata/annotations/gradiated.com~1qualification-error",
      value: candidate.incarnation,
    });
  await request(path, "PATCH", patch);
};
