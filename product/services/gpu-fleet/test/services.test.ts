import { describe, expect, it } from "vitest";

import { GPU_HOSTS, gpuHostSchema, SERVICES } from "../src/hosts.js";
import { reconcileService } from "../src/services.js";
import { fakeKubernetes } from "./support/kubernetes.js";
import { FIRST, gpuHost } from "./support/fleet.js";

const servicePath = `${SERVICES}/gpu-${FIRST}`;

const setup = () => {
  const cluster = fakeKubernetes();
  const host = gpuHostSchema.parse(
    cluster.seed(GPU_HOSTS, gpuHost(FIRST, "pod1")),
  );
  return { cluster, host };
};

// The Service as the inference-hosts Argo application left it, after the
// Tailscale operator pointed it at its proxy group.
const argoService = () => ({
  apiVersion: "v1",
  kind: "Service",
  metadata: {
    name: `gpu-${FIRST}`,
    namespace: "tailscale-inference",
    annotations: {
      "argocd.argoproj.io/tracking-id": `inference-hosts:/Service:tailscale-inference/gpu-${FIRST}`,
      "kubectl.kubernetes.io/last-applied-configuration": "{}",
      "tailscale.com/tailnet-fqdn": `gpu-${FIRST}.tail186117.ts.net`,
      "tailscale.com/proxy-group": "inference-egress",
    },
    finalizers: ["tailscale.com/finalizer"],
  },
  spec: {
    type: "ExternalName",
    externalName: `ts-gpu-${FIRST}-abcde.tailscale-inference.svc.cluster.local`,
    ports: [
      { name: "inference", port: 8888, protocol: "TCP", targetPort: 8888 },
    ],
  },
});

describe("host egress Services", () => {
  it("creates the Service a new host needs, with no owner to cascade a deletion", async () => {
    const { cluster, host } = setup();
    expect(await reconcileService(cluster.api, host)).toBe("created");
    const service = cluster.read(servicePath)!;
    expect(service.metadata).toMatchObject({
      labels: { "app.kubernetes.io/managed-by": "gpu-fleet" },
      annotations: {
        "gradiated.com/instance-id": FIRST,
        "tailscale.com/tailnet-fqdn": `gpu-${FIRST}.tail186117.ts.net`,
        "tailscale.com/proxy-group": "inference-egress",
      },
    });
    expect(service.metadata).not.toHaveProperty("ownerReferences");
    expect(service.spec).toEqual({
      type: "ExternalName",
      externalName: "unused",
      ports: [{ name: "inference", port: 8888, protocol: "TCP" }],
    });
    expect(await reconcileService(cluster.api, host)).toBe("unchanged");
  });

  it("adopts the Service Argo created without changing where it routes", async () => {
    const { cluster, host } = setup();
    cluster.seed(SERVICES, argoService());

    expect(await reconcileService(cluster.api, host)).toBe("adopted");
    const service = cluster.read(servicePath)!;
    const annotations = service.metadata.annotations as Record<string, string>;
    expect(annotations).not.toHaveProperty("argocd.argoproj.io/tracking-id");
    expect(annotations).not.toHaveProperty(
      "kubectl.kubernetes.io/last-applied-configuration",
    );
    expect(annotations["tailscale.com/tailnet-fqdn"]).toBe(
      `gpu-${FIRST}.tail186117.ts.net`,
    );
    expect(service.metadata.finalizers).toEqual(["tailscale.com/finalizer"]);
    expect(service.metadata).not.toHaveProperty("ownerReferences");
    expect((service.spec as { externalName: string }).externalName).toBe(
      argoService().spec.externalName,
    );
    // The server-defaulted targetPort is not drift.
    expect(await reconcileService(cluster.api, host)).toBe("unchanged");
  });

  it("removes a GpuHost owner reference so deleting the GpuHost cannot delete the route", async () => {
    const { cluster, host } = setup();
    const other = {
      apiVersion: "v1",
      kind: "ConfigMap",
      name: "x",
      uid: "other",
    };
    const service = argoService();
    cluster.seed(SERVICES, {
      ...service,
      metadata: {
        ...service.metadata,
        labels: { "app.kubernetes.io/managed-by": "gpu-fleet" },
        ownerReferences: [
          {
            apiVersion: "fleet.gradiated.com/v1alpha1",
            kind: "GpuHost",
            name: `gpu-${FIRST}`,
            uid: host.metadata.uid,
            controller: true,
          },
          other,
        ],
      },
    });

    await reconcileService(cluster.api, host);
    expect(cluster.read(servicePath)!.metadata.ownerReferences).toEqual([
      other,
    ]);
  });

  it("puts back routing that drifted", async () => {
    const { cluster, host } = setup();
    await reconcileService(cluster.api, host);
    const current = cluster.read(servicePath)!;
    cluster.objects.set(servicePath, {
      ...current,
      metadata: {
        ...current.metadata,
        annotations: { "tailscale.com/tailnet-ip": "100.64.0.1" },
      },
    });

    expect(await reconcileService(cluster.api, host)).toBe("updated");
    expect(cluster.read(servicePath)!.metadata.annotations).toEqual({
      "gradiated.com/instance-id": FIRST,
      "tailscale.com/tailnet-fqdn": `gpu-${FIRST}.tail186117.ts.net`,
      "tailscale.com/proxy-group": "inference-egress",
    });
  });
});
