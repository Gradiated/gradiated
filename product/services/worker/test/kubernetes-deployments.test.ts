import { randomUUID } from "node:crypto";
import { describe, expect, it } from "vitest";
import {
  createKubernetesDeploymentView,
  readKubernetesDeployments,
} from "../src/kubernetes-deployments.js";

const release = {
  schema_version: 1,
  runtime_revision: "kev-test",
  model_path: "jaredpalmer/kev-9b",
  model_revision: "pinned",
  tokenizer_path: "tokenizer",
  tokenizer_revision: "pinned",
  protocol: "system_one",
};
const pod = (instanceId = randomUUID()) => ({
  metadata: {
    uid: randomUUID(),
    name: "kev",
    annotations: {
      "gradiated.com/model-id": "jaredpalmer/kev-9b",
      "gradiated.com/release": JSON.stringify(release),
    } as Record<string, string>,
  },
  spec: { nodeName: `gpu-${instanceId}` },
  status: { phase: "Running" },
});

describe("Kubernetes inference deployment discovery", () => {
  it("keeps warm pods unavailable until SDK qualification", () => {
    const candidate = pod();
    expect(readKubernetesDeployments([candidate])[0]).toMatchObject({
      qualified: false,
    });
    candidate.metadata.annotations = {
      ...candidate.metadata.annotations,
      "gradiated.com/qualified": "true",
    };
    expect(readKubernetesDeployments([candidate])[0]).toMatchObject({
      qualified: true,
    });
    expect(
      readKubernetesDeployments([
        {
          ...candidate,
          metadata: { ...candidate.metadata, deletionTimestamp: "now" },
        },
      ])[0],
    ).toMatchObject({ draining: true });
  });

  it("reads all pages before deciding that a deployment disappeared", async () => {
    const first = pod(),
      second = pod();
    const paths: string[] = [];
    const view = createKubernetesDeploymentView(
      "gpu-inference",
      async (path) => {
        paths.push(path);
        return path.includes("continue=")
          ? { items: [second], metadata: {} }
          : { items: [first], metadata: { continue: "next" } };
      },
    );
    await expect(view.isGone(first.metadata.uid)).rejects.toThrow("snapshot");
    expect(await view.running()).toHaveLength(2);
    expect(paths).toHaveLength(2);
    expect(await view.isGone(second.metadata.uid)).toBe(false);
    expect(await view.isGone(randomUUID())).toBe(true);
  });

  it("does not convert a failed API read into an empty fleet", async () => {
    const view = createKubernetesDeploymentView("gpu-inference", async () => {
      throw new Error("API unavailable");
    });
    await expect(view.running()).rejects.toThrow("API unavailable");
    await expect(view.isGone(randomUUID())).rejects.toThrow("snapshot");
  });
});
