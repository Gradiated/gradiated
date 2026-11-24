import { hostName, SERVICES, TAILNET, type GpuHost } from "./hosts.js";
import type { Kubernetes } from "./kubernetes.js";

type Service = {
  metadata: {
    name: string;
    labels?: Record<string, string>;
    annotations?: Record<string, string>;
    ownerReferences?: { kind: string }[];
  };
  spec?: { type?: string; ports?: unknown[] };
};

export type ServiceChange = "created" | "adopted" | "updated" | "unchanged";

export const MANAGED_BY = "gpu-fleet";
const PORTS = [{ name: "inference", port: 8888, protocol: "TCP" }];
// Left by the Argo application that rendered these Services before the
// operator kept them; dropping them takes the Services out of Argo's view.
const RETIRED_ANNOTATIONS = [
  "argocd.argoproj.io/tracking-id",
  "kubectl.kubernetes.io/last-applied-configuration",
];

const labels = { "app.kubernetes.io/managed-by": MANAGED_BY };

const annotations = (host: GpuHost, address?: string) => ({
  "gradiated.com/instance-id": host.spec.instanceId,
  ...(address
    ? { "tailscale.com/tailnet-ip": address }
    : {
        "tailscale.com/tailnet-fqdn": `${hostName(host.spec.instanceId)}.${TAILNET}`,
      }),
  "tailscale.com/proxy-group": "inference-egress",
});

// Services carry no ownerReferences: garbage collection would delete a serving
// host's route whenever its GpuHost or the CRD is deleted. The operator never
// deletes Services. The Tailscale operator owns spec.externalName.
export const reconcileService = async (
  api: Kubernetes,
  host: GpuHost,
  enrollmentTarget?: { address: string | undefined },
): Promise<ServiceChange> => {
  const name = hostName(host.spec.instanceId);
  const existing = (await api.get(`${SERVICES}/${name}`)) as
    Service | undefined;
  const address =
    enrollmentTarget &&
    (enrollmentTarget.address ??
      existing?.metadata.annotations?.["tailscale.com/tailnet-ip"]);
  if (!existing) {
    await api.create(SERVICES, {
      apiVersion: "v1",
      kind: "Service",
      metadata: {
        name,
        namespace: "tailscale-inference",
        labels,
        annotations: annotations(host, address),
      },
      spec: { type: "ExternalName", externalName: "unused", ports: PORTS },
    });
    return "created";
  }

  const current = existing.metadata;
  const patch: { metadata: Record<string, unknown>; spec?: unknown } = {
    metadata: {},
  };
  const adopted =
    current.labels?.["app.kubernetes.io/managed-by"] !== MANAGED_BY;

  if (adopted) patch.metadata.labels = labels;
  const references = current.ownerReferences ?? [];
  if (references.some((reference) => reference.kind === "GpuHost"))
    patch.metadata.ownerReferences = references.filter(
      (reference) => reference.kind !== "GpuHost",
    );
  const annotationPatch: Record<string, string | null> = {};
  for (const [key, value] of Object.entries(annotations(host, address)))
    if (current.annotations?.[key] !== value) annotationPatch[key] = value;
  const obsoleteTarget = address
    ? "tailscale.com/tailnet-fqdn"
    : "tailscale.com/tailnet-ip";
  for (const key of [...RETIRED_ANNOTATIONS, obsoleteTarget])
    if (current.annotations?.[key] !== undefined) annotationPatch[key] = null;
  if (Object.keys(annotationPatch).length)
    patch.metadata.annotations = annotationPatch;

  // The API server adds targetPort, so compare only the fields set here.
  const ports = (existing.spec?.ports ?? []).map((port) => {
    const { name, port: number, protocol } = port as Record<string, unknown>;
    return { name, port: number, protocol };
  });
  if (
    existing.spec?.type !== "ExternalName" ||
    JSON.stringify(ports) !== JSON.stringify(PORTS)
  )
    patch.spec = { type: "ExternalName", ports: PORTS };

  if (!Object.keys(patch.metadata).length && !patch.spec) return "unchanged";
  await api.mergePatch(`${SERVICES}/${name}`, patch);
  return adopted ? "adopted" : "updated";
};
