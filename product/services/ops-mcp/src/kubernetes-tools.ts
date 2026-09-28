import { z } from "zod";

import type { Backend } from "./backend.js";
import type { RegisterReadTool } from "./tools.js";

const namespace = z.enum([
  "gradiated",
  "observability",
  "argocd",
  "kube-system",
  "external-secrets",
  "nomad",
]);
const selector = z.string().min(1).max(500).optional();
const resourceName = z
  .string()
  .regex(/^[a-z0-9]([-a-z0-9.]*[a-z0-9])?$/)
  .max(253);
const status = z.record(z.string(), z.unknown()).optional();
const condition = z.object({
  type: z.string(),
  status: z.string().optional(),
  reason: z.string().optional(),
  lastTransitionTime: z.string().optional(),
});
const continue_token = z.string().min(1).max(4096).optional();
const listMetadata = z.object({ continue: z.string().optional() }).optional();

const containerState = z
  .object({
    running: z.object({ startedAt: z.string().optional() }).optional(),
    waiting: z.object({ reason: z.string().optional() }).optional(),
    terminated: z
      .object({
        reason: z.string().optional(),
        exitCode: z.number(),
        startedAt: z.string().optional(),
        finishedAt: z.string().optional(),
      })
      .optional(),
  })
  .optional();

const podList = z.object({
  metadata: listMetadata,
  items: z.array(
    z.object({
      metadata: z.object({
        name: z.string(),
        namespace: z.string(),
        labels: z.record(z.string(), z.string()).optional(),
        ownerReferences: z
          .array(z.object({ kind: z.string(), name: z.string() }))
          .optional(),
      }),
      spec: z.object({
        nodeName: z.string().optional(),
        containers: z.array(
          z.object({
            name: z.string(),
            resources: z.record(z.string(), z.unknown()).optional(),
          }),
        ),
      }),
      status: z.object({
        phase: z.string().optional(),
        reason: z.string().optional(),
        startTime: z.string().optional(),
        conditions: z.array(condition).optional(),
        containerStatuses: z
          .array(
            z.object({
              name: z.string(),
              ready: z.boolean(),
              restartCount: z.number(),
              image: z.string(),
              state: containerState,
              lastState: containerState,
            }),
          )
          .optional(),
      }),
    }),
  ),
});

const workloadList = z.object({
  metadata: listMetadata,
  items: z.array(
    z.object({
      metadata: z.object({
        name: z.string(),
        creationTimestamp: z.string().optional(),
        generation: z.number().optional(),
        annotations: z.record(z.string(), z.string()).optional(),
        ownerReferences: z
          .array(z.object({ kind: z.string(), name: z.string() }))
          .optional(),
      }),
      spec: z.object({
        replicas: z.number().optional(),
        template: z
          .object({
            spec: z.object({
              containers: z.array(
                z.object({ name: z.string(), image: z.string() }),
              ),
            }),
          })
          .optional(),
      }),
      status,
    }),
  ),
});

const applicationSource = z.object({
  repoURL: z.string().optional(),
  path: z.string().optional(),
  chart: z.string().optional(),
  targetRevision: z.string().optional(),
});

const initiatedBy = z
  .object({
    username: z.string().optional(),
    automated: z.boolean().optional(),
  })
  .optional();

const application = z.object({
  metadata: z.object({ name: z.string() }),
  spec: z.object({
    project: z.string().optional(),
    source: applicationSource.optional(),
    sources: z.array(applicationSource).optional(),
    destination: z
      .object({
        namespace: z.string().optional(),
        server: z.string().optional(),
      })
      .optional(),
    syncPolicy: z.object({ automated: z.unknown().optional() }).optional(),
  }),
  status: z
    .object({
      reconciledAt: z.string().optional(),
      sync: z
        .object({
          status: z.string().optional(),
          revision: z.string().optional(),
          revisions: z.array(z.string()).optional(),
        })
        .optional(),
      health: z
        .object({
          status: z.string().optional(),
          message: z.string().optional(),
          lastTransitionTime: z.string().optional(),
        })
        .optional(),
      conditions: z
        .array(condition.extend({ message: z.string().optional() }))
        .optional(),
      operationState: z
        .object({
          phase: z.string().optional(),
          message: z.string().optional(),
          startedAt: z.string().optional(),
          finishedAt: z.string().optional(),
          operation: z.object({ initiatedBy }).optional(),
          syncResult: z
            .object({
              revision: z.string().optional(),
              revisions: z.array(z.string()).optional(),
            })
            .optional(),
        })
        .optional(),
      history: z
        .array(
          z.object({
            id: z.number(),
            revision: z.string().optional(),
            revisions: z.array(z.string()).optional(),
            deployedAt: z.string().optional(),
            deployStartedAt: z.string().optional(),
            initiatedBy,
          }),
        )
        .optional(),
      resources: z
        .array(
          z.object({
            kind: z.string(),
            name: z.string(),
            namespace: z.string().optional(),
            status: z.string().optional(),
            health: z
              .object({
                status: z.string().optional(),
                message: z.string().optional(),
              })
              .optional(),
          }),
        )
        .optional(),
    })
    .optional(),
});

const REVISION = "deployment.kubernetes.io/revision";
const WORKLOAD_KINDS = [
  "deployments",
  "statefulsets",
  "daemonsets",
  "replicasets",
] as const;

// Pod specs carry literal environment variables and command arguments, and
// status messages can quote them, so only named diagnostic fields leave.
export const projectPods = (data: unknown) => {
  const { metadata, items } = podList.parse(data);

  return {
    pods: items.map(({ metadata, spec, status }) => ({
      ...metadata,
      node: spec.nodeName,
      resources: spec.containers.map(({ name, resources }) => ({
        name,
        resources,
      })),
      ...status,
    })),
    continue_token: metadata?.continue || undefined,
  };
};

export const projectWorkloads = (data: unknown) => {
  const { metadata, items } = workloadList.parse(data);

  return {
    items: items.map(({ metadata, spec, status }) => ({
      name: metadata.name,
      createdAt: metadata.creationTimestamp,
      generation: metadata.generation,
      revision: metadata.annotations?.[REVISION],
      owner: metadata.ownerReferences?.[0],
      replicas: spec.replicas,
      images: spec.template?.spec.containers,
      status,
    })),
    continue_token: metadata?.continue || undefined,
  };
};

type ApplicationStatus = NonNullable<z.output<typeof application>["status"]>;
type OperationState = NonNullable<ApplicationStatus["operationState"]>;
type ApplicationResource = NonNullable<ApplicationStatus["resources"]>[number];

const projectOperation = ({ operation, ...state }: OperationState) => ({
  ...state,
  initiatedBy: operation?.initiatedBy,
});

const isOutOfSyncOrUnhealthy = ({ status, health }: ApplicationResource) =>
  (status !== undefined && status !== "Synced") ||
  (health?.status !== undefined && health.status !== "Healthy");

export const projectApplication = (data: unknown, historyLimit: number) => {
  const { metadata, spec, status } = application.parse(data);

  return {
    name: metadata.name,
    project: spec.project,
    sources: spec.sources ?? (spec.source ? [spec.source] : []),
    destination: spec.destination,
    automated: spec.syncPolicy?.automated !== undefined,
    reconciledAt: status?.reconciledAt,
    sync: status?.sync,
    health: status?.health,
    conditions: status?.conditions,
    lastOperation:
      status?.operationState && projectOperation(status.operationState),
    history: status?.history?.slice(-historyLimit).reverse(),
    outOfSyncOrUnhealthy: status?.resources?.filter(isOutOfSyncOrUnhealthy),
  };
};

export const registerKubernetesTools = (
  register: RegisterReadTool,
  backend: Backend,
) => {
  register(
    "workload_status",
    'Pods in one EKS namespace: phase, conditions, start time, owner, labels, node, container images, readiness, restart counts, current state and lastState (the previous termination reason such as OOMKilled or Error, exit code and times), and resource requests and limits. Environment, arguments and annotations are never returned. label_selector (for example app.kubernetes.io/name=worker) and field_selector (for example status.phase!=Running) narrow the list. When continue_token is returned, more pods exist; pass it back to read the next page. For Kubernetes events, query_logs {workload="kubernetes-events"}.',
    {
      namespace,
      label_selector: selector,
      field_selector: selector,
      limit: z.number().int().min(1).max(500).default(100),
      continue_token,
    },
    async ({
      namespace,
      label_selector,
      field_selector,
      limit,
      continue_token,
    }) =>
      projectPods(
        await backend("kubernetes", `/api/v1/namespaces/${namespace}/pods`, {
          limit: String(limit),
          ...(label_selector && { labelSelector: label_selector }),
          ...(field_selector && { fieldSelector: field_selector }),
          ...(continue_token && { continue: continue_token }),
        }),
      ),
  );

  register(
    "rollouts",
    "Deployments, StatefulSets, DaemonSets and ReplicaSets in one EKS namespace: images, desired replicas, generation, full status (ready, updated and available replicas, conditions such as ProgressDeadlineExceeded, current and update revisions) and creation times. ReplicaSets carry the Deployment revision and owner, so they form the rollout history: which image each revision ran and when it was created. Each kind returns up to 500 items; a continue_token means more exist, so read the next page with that one kind and the token. Use it to answer what changed and when; use argocd_applications for the Git revision behind it.",
    {
      namespace,
      kinds: z.array(z.enum(WORKLOAD_KINDS)).min(1).optional(),
      label_selector: selector,
      continue_token,
    },
    async ({ namespace, kinds, label_selector, continue_token }) => {
      const selected = kinds ?? WORKLOAD_KINDS;
      if (continue_token && selected.length !== 1) {
        throw new Error("continue_token_needs_one_kind");
      }

      const lists = await Promise.all(
        selected.map(async (kind) =>
          projectWorkloads(
            await backend(
              "kubernetes",
              `/apis/apps/v1/namespaces/${namespace}/${kind}`,
              {
                limit: "500",
                ...(label_selector && { labelSelector: label_selector }),
                ...(continue_token && { continue: continue_token }),
              },
            ),
          ),
        ),
      );

      return Object.fromEntries(
        selected.map((kind, index) => [kind, lists[index]]),
      );
    },
  );

  register(
    "argocd_applications",
    "Argo CD applications: source repository, path and target revision, destination, whether sync is automated, sync status and deployed Git revision, health, conditions (sync and comparison errors), the last sync operation (phase, message, times, who started it), recent deployment history (revision and deployedAt, newest first) and the resources that are out of sync or unhealthy. Helm values are never returned. A continue_token means more applications exist; pass it back for the next page. Use it to line up an incident with a deploy: compare deployedAt with the onset time, then read the revision in Git.",
    {
      name: resourceName.optional(),
      history_limit: z.number().int().min(1).max(50).default(5),
      continue_token,
    },
    async ({ name, history_limit, continue_token }) => {
      const path = "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications";

      if (name) {
        return projectApplication(
          await backend("kubernetes", `${path}/${name}`),
          history_limit,
        );
      }

      const { metadata, items } = z
        .object({ metadata: listMetadata, items: z.array(z.unknown()) })
        .parse(
          await backend("kubernetes", path, {
            limit: "500",
            ...(continue_token && { continue: continue_token }),
          }),
        );

      return {
        applications: items.map((item) =>
          projectApplication(item, history_limit),
        ),
        continue_token: metadata?.continue || undefined,
      };
    },
  );

  register(
    "node_status",
    "EKS node conditions (Ready, MemoryPressure, DiskPressure, PIDPressure), capacity and allocatable resources. GPU hosts are not EKS nodes; use nomad with resource=nodes for them.",
    {},
    async () => {
      const data = z
        .object({
          items: z.array(
            z.object({
              metadata: z.object({ name: z.string() }),
              status: z.object({
                capacity: z.record(z.string(), z.string()).optional(),
                allocatable: z.record(z.string(), z.string()).optional(),
                conditions: z
                  .array(
                    z.object({
                      type: z.string(),
                      status: z.string(),
                      reason: z.string().optional(),
                      lastTransitionTime: z.string().optional(),
                    }),
                  )
                  .optional(),
              }),
            }),
          ),
        })
        .parse(await backend("kubernetes", "/api/v1/nodes", { limit: "100" }));

      return {
        nodes: data.items.map(({ metadata, status }) => ({
          name: metadata.name,
          ...status,
        })),
        possibly_truncated: true,
      };
    },
  );
};
