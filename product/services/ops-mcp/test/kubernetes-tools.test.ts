import { afterEach, describe, expect, it } from "vitest";

import { callTool, closeServers } from "./support/mcp.js";

afterEach(closeServers);

const replicaSet = {
  metadata: {
    name: "worker-8cc69bc97",
    creationTimestamp: "2026-09-25T21:10:00Z",
    annotations: {
      "deployment.kubernetes.io/revision": "42",
      "kubectl.kubernetes.io/last-applied-configuration": "PRIVATE",
    },
    ownerReferences: [{ kind: "Deployment", name: "worker" }],
  },
  spec: {
    replicas: 3,
    template: {
      spec: {
        containers: [
          {
            name: "worker",
            image: "product@sha256:abc",
            env: [{ value: "PRIVATE" }],
          },
        ],
      },
    },
  },
  status: { replicas: 3, readyReplicas: 3 },
};

const application = {
  metadata: { name: "workloads" },
  spec: {
    project: "default",
    source: {
      repoURL: "git@github.com:Gradiated/gradiated.git",
      path: "infra/workloads",
      targetRevision: "main",
      helm: { valuesObject: { password: "PRIVATE" } },
    },
    destination: { namespace: "gradiated" },
    syncPolicy: { automated: { prune: true } },
  },
  status: {
    sync: { status: "Synced", revision: "c9143de5" },
    health: { status: "Degraded" },
    operationState: {
      phase: "Succeeded",
      finishedAt: "2026-09-25T21:12:00Z",
      operation: {
        initiatedBy: { automated: true },
        sync: { manifests: ["PRIVATE"] },
      },
      syncResult: { revision: "c9143de5", resources: [{ message: "PRIVATE" }] },
    },
    history: [1, 2, 3].map((id) => ({
      id,
      revision: `rev-${id}`,
      deployedAt: `2026-09-2${id}T00:00:00Z`,
      source: { helm: { values: "PRIVATE" } },
    })),
    resources: [
      {
        kind: "Deployment",
        name: "worker",
        status: "Synced",
        health: { status: "Healthy" },
      },
      {
        kind: "Deployment",
        name: "api",
        status: "Synced",
        health: { status: "Progressing" },
      },
      { kind: "ConfigMap", name: "settings", status: "OutOfSync" },
    ],
  },
};

describe("kubernetes tools", () => {
  it("reads each workload kind and keeps the revision history without annotations or environment", async () => {
    const { backend, body } = await callTool(
      "rollouts",
      { namespace: "gradiated", kinds: ["replicasets"] },
      { items: [replicaSet] },
    );

    expect(backend).toHaveBeenCalledWith(
      "kubernetes",
      "/apis/apps/v1/namespaces/gradiated/replicasets",
      { limit: "500" },
    );
    expect(JSON.stringify(body)).not.toContain("PRIVATE");
    expect(body).toEqual({
      replicasets: [
        {
          name: "worker-8cc69bc97",
          createdAt: "2026-09-25T21:10:00Z",
          revision: "42",
          owner: { kind: "Deployment", name: "worker" },
          replicas: 3,
          images: [{ name: "worker", image: "product@sha256:abc" }],
          status: { replicas: 3, readyReplicas: 3 },
        },
      ],
    });
  });

  it("reads all workload kinds by default", async () => {
    const { backend } = await callTool(
      "rollouts",
      { namespace: "nomad", label_selector: "app=nomad" },
      { items: [] },
    );

    expect(backend.mock.calls.map((call) => (call as unknown[])[1])).toEqual([
      "/apis/apps/v1/namespaces/nomad/deployments",
      "/apis/apps/v1/namespaces/nomad/statefulsets",
      "/apis/apps/v1/namespaces/nomad/daemonsets",
      "/apis/apps/v1/namespaces/nomad/replicasets",
    ]);
  });

  it("summarizes an application's deploys and unhealthy resources without Helm values or manifests", async () => {
    const { backend, body } = await callTool(
      "argocd_applications",
      { name: "workloads", history_limit: 2 },
      application,
    );

    expect(backend).toHaveBeenCalledWith(
      "kubernetes",
      "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/workloads",
    );
    expect(JSON.stringify(body)).not.toContain("PRIVATE");
    expect(body).toMatchObject({
      name: "workloads",
      automated: true,
      sources: [{ path: "infra/workloads", targetRevision: "main" }],
      sync: { status: "Synced", revision: "c9143de5" },
      health: { status: "Degraded" },
      lastOperation: {
        phase: "Succeeded",
        initiatedBy: { automated: true },
        syncResult: { revision: "c9143de5" },
      },
      history: [
        { id: 3, revision: "rev-3" },
        { id: 2, revision: "rev-2" },
      ],
      outOfSyncOrUnhealthy: [
        { kind: "Deployment", name: "api" },
        { kind: "ConfigMap", name: "settings" },
      ],
    });
  });

  it("lists every application when no name is given", async () => {
    const { body } = await callTool(
      "argocd_applications",
      {},
      { items: [application] },
    );

    expect(body).toMatchObject({ applications: [{ name: "workloads" }] });
  });

  it.each([
    ["argocd_applications", { name: "../secrets" }],
    ["rollouts", { namespace: "default" }],
    ["workload_status", { namespace: "kube-public" }],
  ])("rejects %s with %o", async (name, args) => {
    const { backend, isError } = await callTool(name, args);

    expect(isError).toBe(true);
    expect(backend).not.toHaveBeenCalled();
  });

  it("passes pod selectors through", async () => {
    const { backend } = await callTool(
      "workload_status",
      {
        namespace: "gradiated",
        label_selector: "app.kubernetes.io/name=worker",
        field_selector: "status.phase!=Running",
      },
      { items: [] },
    );

    expect(backend).toHaveBeenCalledWith(
      "kubernetes",
      "/api/v1/namespaces/gradiated/pods",
      {
        limit: "100",
        labelSelector: "app.kubernetes.io/name=worker",
        fieldSelector: "status.phase!=Running",
      },
    );
  });
});
