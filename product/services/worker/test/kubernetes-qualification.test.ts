import { randomUUID } from "node:crypto";
import { describe, it, expect } from "vitest";
import {
  qualifyKubernetesPod,
  qualificationCandidate,
} from "../src/kubernetes-qualification.js";

const pod = () => ({
  metadata: {
    uid: randomUUID(),
    name: "kev",
    resourceVersion: "1",
    annotations: {
      "gradiated.com/model-id": "jaredpalmer/kev-9b",
      "gradiated.com/release": JSON.stringify({
        schema_version: 1,
        runtime_revision: "kev-a",
        model_path: "kev",
        model_revision: "pinned",
        tokenizer_path: "kev",
        tokenizer_revision: "pinned",
        protocol: "system_one",
      }),
    } as Record<string, string>,
  },
  spec: { nodeName: "gpu-" + randomUUID() },
  status: {
    conditions: [{ type: "RuntimeReady", status: "True" }],
    containerStatuses: [{ containerID: "runpod://1:100" }],
  },
});

const availableModels = new Set(["jaredpalmer/kev-9b"]);

describe("Kubernetes SDK qualification", () => {
  it("gates qualification on runtime readiness and process incarnation", () => {
    const candidate = pod();
    expect(qualificationCandidate(candidate)).toBeDefined();
    candidate.status.conditions[0]!.status = "False";
    expect(qualificationCandidate(candidate)).toBeUndefined();
    candidate.status.conditions[0]!.status = "True";
    candidate.metadata.annotations["gradiated.com/qualified"] = "true";
    candidate.metadata.annotations["gradiated.com/qualified-runtime"] =
      "runpod://1:100";
    expect(qualificationCandidate(candidate)).toBeUndefined();
    candidate.status.containerStatuses[0]!.containerID = "runpod://2:200";
    expect(qualificationCandidate(candidate)).toBeDefined();
  });
  it("publishes only the UID and process that passed the SDK", async () => {
    const current = pod();
    let patch: unknown;
    const request = async (path: string, method?: string, body?: unknown) => {
      if (method === "PATCH") {
        patch = body;
        return current;
      }
      return path.includes("?") ? { items: [current], metadata: {} } : current;
    };
    await qualifyKubernetesPod(
      "gpu-inference",
      request,
      availableModels,
      async (input) => {
        expect(input).toMatchObject({
          stage: "canary",
          deploymentIds: [current.metadata.uid],
        });
      },
    );
    expect(patch).toEqual(
      expect.arrayContaining([
        { op: "test", path: "/metadata/uid", value: current.metadata.uid },
        {
          op: "add",
          path: "/metadata/annotations/gradiated.com~1qualified-runtime",
          value: "runpod://1:100",
        },
      ]),
    );
  });
  it("does not publish a process that restarted during SDK verification", async () => {
    const current = pod();
    let patched = false;
    const request = async (path: string, method?: string) => {
      if (method === "PATCH") patched = true;
      return path.includes("?") ? { items: [current], metadata: {} } : current;
    };
    await qualifyKubernetesPod(
      "gpu-inference",
      request,
      availableModels,
      async () => {
        current.status.containerStatuses[0]!.containerID = "runpod://2:200";
      },
    );
    expect(patched).toBe(false);
  });
  it("waits for catalog availability without rejecting the runtime incarnation", async () => {
    const current = pod();
    let verifications = 0;
    let patches = 0;
    const request = async (path: string, method?: string) => {
      if (method === "PATCH") patches += 1;
      return path.includes("?") ? { items: [current], metadata: {} } : current;
    };
    const verify = async () => {
      verifications += 1;
    };

    await qualifyKubernetesPod("gpu-inference", request, new Set(), verify);
    expect(verifications).toBe(0);
    expect(patches).toBe(0);

    await qualifyKubernetesPod(
      "gpu-inference",
      request,
      availableModels,
      verify,
    );
    expect(verifications).toBe(1);
    expect(patches).toBe(1);
  });
  it("records a rejected incarnation without qualifying it", async () => {
    const current = pod();
    let patch: unknown;
    const request = async (path: string, method?: string, body?: unknown) => {
      if (method === "PATCH") {
        patch = body;
        return current;
      }
      return path.includes("?") ? { items: [current], metadata: {} } : current;
    };
    await qualifyKubernetesPod(
      "gpu-inference",
      request,
      availableModels,
      async () => {
        throw new Error("bad model response");
      },
    );
    expect(patch).toEqual(
      expect.arrayContaining([
        {
          op: "add",
          path: "/metadata/annotations/gradiated.com~1qualification-error",
          value: "runpod://1:100",
        },
      ]),
    );
    expect(JSON.stringify(patch)).not.toContain('"value":"true"');
  });
});
