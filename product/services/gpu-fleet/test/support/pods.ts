// Pods as gpu-controller publishes them, from production on 2026-10-23: condition
// times and startedAt are null (Go's zero metav1.Time). Images and IDs are placeholders.

const IMAGE = "registry.example/inference:placeholder";

const condition = (type: string, ready: boolean) => ({
  lastProbeTime: null,
  lastTransitionTime: null,
  status: ready ? "True" : "False",
  type,
});

export const virtualKubeletStatus = (ready: boolean) => ({
  phase: "Running",
  conditions: [
    condition("RuntimeReady", ready),
    condition("Ready", ready),
    condition("ContainersReady", ready),
    condition("Initialized", true),
    condition("PodScheduled", true),
  ],
  containerStatuses: [
    {
      name: "inference",
      image: IMAGE,
      ready,
      containerID: "runpod://4242:2026-10-23T09:12:44Z",
      state: { running: { startedAt: null } },
    },
  ],
});

// A serving model pod bound to a GPU host. Its ReplicaSet is the name without
// the last part, as deepseek-5867b44cff owns deepseek-5867b44cff-x2k9p.
export const virtualKubeletPod = (
  model: string,
  name: string,
  node: string,
  ready = true,
) => ({
  apiVersion: "v1",
  kind: "Pod",
  metadata: {
    name,
    namespace: "gpu-inference",
    uid: `${name}-uid`,
    labels: { "app.kubernetes.io/name": model },
    annotations: {
      "gradiated.com/qualified": "true",
      "gradiated.com/qualified-runtime": `${name}:1`,
    },
    ownerReferences: [
      {
        apiVersion: "apps/v1",
        blockOwnerDeletion: true,
        controller: true,
        kind: "ReplicaSet",
        name: name.slice(0, name.lastIndexOf("-")),
        uid: `${model}-replicaset-uid`,
      },
    ],
  },
  spec: {
    nodeName: node,
    containers: [
      {
        name: "inference",
        image: IMAGE,
        resources: {
          limits: { cpu: "32", memory: "400Gi", "nvidia.com/gpu": "4" },
          requests: { cpu: "32", memory: "400Gi", "nvidia.com/gpu": "4" },
        },
      },
    ],
  },
  status: virtualKubeletStatus(ready),
});
