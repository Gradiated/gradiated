import { createKubernetesRequest } from "@gradiated/control";
export { createKubernetesRequest } from "@gradiated/control";
import { z } from "zod";
import {
  KubernetesDeploymentSchema,
  type KubernetesDeploymentView,
} from "@gradiated/control";

const podSchema = z.object({
  metadata: z.object({
    uid: z.uuid(),
    name: z.string(),
    annotations: z.record(z.string(), z.string()).default({}),
    deletionTimestamp: z.string().optional(),
  }),
  spec: z.object({ nodeName: z.string().optional() }),
  status: z
    .object({
      phase: z.string().optional(),
      conditions: z
        .array(z.object({ type: z.string(), status: z.string() }))
        .default([]),
    })
    .default({ conditions: [] }),
});
const listSchema = z.object({
  items: z.array(podSchema),
  metadata: z.object({ continue: z.string().optional() }),
});

export const readKubernetesDeployments = (items: unknown[]) =>
  podSchema
    .array()
    .parse(items)
    .flatMap((pod) => {
      const instanceId = pod.spec.nodeName?.match(/^gpu-([0-9a-f-]{36})$/)?.[1];
      const annotations = pod.metadata.annotations;
      if (
        !instanceId ||
        !annotations["gradiated.com/model-id"] ||
        !annotations["gradiated.com/release"]
      )
        return [];

      let release: unknown;
      try {
        release = JSON.parse(annotations["gradiated.com/release"]);
      } catch {
        return [];
      }

      const parsed = KubernetesDeploymentSchema.safeParse({
        id: pod.metadata.uid,
        name: pod.metadata.name,
        instanceId,
        modelId: annotations["gradiated.com/model-id"],
        release,
        qualified:
          annotations["gradiated.com/qualified"] === "true" &&
          pod.status.phase === "Running" &&
          pod.status.conditions.some(
            (condition) =>
              condition.type === "Ready" && condition.status === "True",
          ),
        draining: Boolean(pod.metadata.deletionTimestamp),
      });
      return parsed.success ? [parsed.data] : [];
    });

export const createKubernetesDeploymentView = (
  namespace: string,
  get: (path: string) => Promise<unknown>,
): KubernetesDeploymentView => {
  let known: Set<string> | undefined;
  return {
    running: async () => {
      const pods: z.infer<typeof podSchema>[] = [];
      let continuation = "";
      do {
        const page = listSchema.parse(
          await get(
            `/api/v1/namespaces/${encodeURIComponent(namespace)}/pods?limit=250${continuation ? `&continue=${encodeURIComponent(continuation)}` : ""}`,
          ),
        );
        pods.push(...page.items);
        continuation = page.metadata.continue ?? "";
      } while (continuation);
      const running = readKubernetesDeployments(pods);
      known = new Set(pods.map((pod) => pod.metadata.uid));
      return running;
    },
    isGone: async (id) => {
      if (!known)
        throw new Error("Kubernetes deployment snapshot has not completed");
      return !known.has(id);
    },
  };
};

export const createKubernetesGet = (signal: AbortSignal) => {
  const request = createKubernetesRequest(signal);
  return (path: string) => request(path);
};
