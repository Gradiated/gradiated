import { X509Certificate } from "node:crypto";

import type { InstanceRecord, InstanceService } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";

import type { InstanceProvider } from "../../src/instances/provider.js";
import {
  createRegistrations,
  type Registration,
  type RegistrationDependencies,
} from "../../src/instances/registration.js";
import { kmsSigner } from "@gradiated/nomad-pki";
import { fakeKms, testCa } from "@gradiated/nomad-pki/testing";

const INSTANCE_ID = "019d5a4a-0000-7000-8000-000000000001";
const BOUND_NODE = "3f1e5a52-8d4b-4c1e-9a55-111111111111";
const TOKEN = "t".repeat(40);
const STATUS_TOKEN = "s".repeat(40);
const ARTIFACT = {
  accessKeyId: "AKIAEXAMPLEEXAMPLE12",
  secretAccessKey: "abcdEFGHijklMNOPqrstUVWXyz0123456789+/ab",
};

const setup = ({
  stopped = true,
  boundNodeId = null as string | null,
  machineEnvironment = {} as Record<string, string>,
  nodeAlreadyJoined = false,
  nodeStatus = "ready",
  supportsInPlace = false,
  sshUnavailable = false,
} = {}) => {
  const bootstraps: {
    environment: Readonly<Record<string, string>>;
    options?: { readonly allowReset?: boolean };
  }[] = [];
  const provider: InstanceProvider = {
    describe: async (id) => ({
      provider: "runpod",
      providerAccountId: "user_1",
      providerInstanceId: id,
      region: "US-NE-1",
      faultDomain: "runpod:machine1",
      sku: "2x NVIDIA RTX PRO 6000",
    }),
    environment: async (_id, options) => {
      if (sshUnavailable && !options?.providerOnly)
        throw new Error("SSH unavailable");

      return machineEnvironment;
    },
    isStopped: async () => stopped,
    supportsInPlace: async () => supportsInPlace,
    bootstrap: async (_instance, _image, environment, options) => {
      bootstraps.push({ environment, options });
    },
  };
  const bindNomadNode = vi.fn(async () => ({}) as InstanceRecord);
  const register = vi.fn(
    async () =>
      ({ id: INSTANCE_ID, nomadNodeId: boundNodeId }) as InstanceRecord,
  );
  const audit = vi.fn();
  const dependencies: RegistrationDependencies = {
    providers: { runpod: async () => provider },
    instances: async () =>
      ({ register, bindNomadNode }) as unknown as InstanceService,
    certificateCredentials: async () =>
      ({
        enroll: async () => "r".repeat(43),
      }) as unknown as import("@gradiated/control").InstanceCertificateService,
    hostImage: "registry.example/nomad-base:inputs-abc",
    caCertificate: async () => testCa.certificate,
    signer: kmsSigner("alias/test-nomad-ca", fakeKms().client),
    runtimeReader: async () => ARTIFACT,
    servingTokens: async () => ({
      runtimeAccess: TOKEN,
      deploymentStatus: STATUS_TOKEN,
    }),
    readNode: async (nodeId) =>
      bootstraps.length === 0 && !nodeAlreadyJoined
        ? null
        : {
            ID: nodeId,
            Name: "runpod-pod1",
            Status: nodeStatus,
            Meta: { gradiated_instance_id: INSTANCE_ID },
          },
    audit,
    nodeTimeoutMs: 50,
  };

  return {
    registrations: createRegistrations(dependencies),
    bootstraps,
    register,
    bindNomadNode,
    audit,
  };
};

const carriedEnvironment = {
  GRADIATED_INSTANCE_ID: INSTANCE_ID,
  GRADIATED_NOMAD_NODE_ID: BOUND_NODE,
  GRADIATED_NOMAD_NODE_SECRET: "3f1e5a52-8d4b-4c1e-9a55-222222222222",
};

const request = {
  provider: "runpod",
  providerInstanceId: "pod1",
  resetRunningPod: false,
  requestedBy: "tester@gradiated.com",
};

const settled = async (
  registrations: ReturnType<typeof setup>["registrations"],
  id: string,
): Promise<Registration> => {
  for (;;) {
    const registration = registrations.get(id)!;
    if (registration.phase === "bound" || registration.phase === "failed") {
      return registration;
    }
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
};

describe("instance registration", () => {
  it("allows an explicitly authorized reset even when the in-place SSH identity is unavailable", async () => {
    const test = setup({
      stopped: false,
      supportsInPlace: true,
      sshUnavailable: true,
    });

    const finished = await settled(
      test.registrations,
      (await test.registrations.start({ ...request, resetRunningPod: true }))
        .id,
    );

    expect(finished).toMatchObject({ phase: "bound", resetRunningPod: true });
    expect(test.bootstraps[0]?.options).toEqual({ allowReset: true });
  });

  it("records, certifies and binds a running pod using in-place bootstrap without allowing reset", async () => {
    const test = setup({ stopped: false, supportsInPlace: true });

    const finished = await settled(
      test.registrations,
      (await test.registrations.start(request)).id,
    );

    expect(finished).toMatchObject({ phase: "bound", resetRunningPod: false });
    expect(test.bootstraps[0]?.options).toEqual({ allowReset: false });
    expect(test.bindNomadNode).toHaveBeenCalledWith(
      INSTANCE_ID,
      finished.nomadNodeId,
    );
  });

  it("records, certifies, boots and binds a stopped machine in order", async () => {
    const test = setup();

    const started = await test.registrations.start(request);
    const finished = await settled(test.registrations, started.id);

    expect(finished).toMatchObject({
      phase: "bound",
      instanceId: INSTANCE_ID,
      nodeName: "runpod-pod1",
      requestedBy: "tester@gradiated.com",
    });
    expect(test.audit.mock.calls.map(([event]) => event.phase)).toEqual([
      "recording",
      "issuing_certificate",
      "updating_provider",
      "waiting_for_node",
      "bound",
    ]);
    expect(test.bindNomadNode).toHaveBeenCalledWith(
      INSTANCE_ID,
      finished.nomadNodeId,
    );
    expect(test.bootstraps[0]?.options).toEqual({ allowReset: false });
  });

  it("boots the machine with a CA-signed certificate and the serving tokens", async () => {
    const test = setup();

    await settled(
      test.registrations,
      (await test.registrations.start(request)).id,
    );

    const environment = test.bootstraps[0]!.environment;
    const decode = (name: string) =>
      Buffer.from(environment[name] ?? "", "base64").toString();
    expect(
      new X509Certificate(decode("GRADIATED_NOMAD_CERT")).verify(
        new X509Certificate(testCa.certificate).publicKey,
      ),
    ).toBe(true);
    expect(decode("GRADIATED_NOMAD_CA")).toBe(testCa.certificate);
    expect(environment).toMatchObject({
      GRADIATED_INSTANCE_ID: INSTANCE_ID,
      GRADIATED_RUNTIME_ACCESS_TOKEN: TOKEN,
      GRADIATED_DEPLOYMENT_STATUS_TOKEN: STATUS_TOKEN,
    });
  });

  it("never writes a secret into the audit trail", async () => {
    const test = setup();

    await settled(
      test.registrations,
      (await test.registrations.start(request)).id,
    );

    const trail = JSON.stringify(test.audit.mock.calls);
    for (const secret of [
      TOKEN,
      STATUS_TOKEN,
      ARTIFACT.secretAccessKey,
      "PRIVATE KEY",
    ]) {
      expect(trail).not.toContain(secret);
    }
  });

  it("returns a bound machine to Nomad as the same node", async () => {
    const test = setup({
      boundNodeId: BOUND_NODE,
      machineEnvironment: carriedEnvironment,
    });

    await settled(
      test.registrations,
      (await test.registrations.start(request)).id,
    );

    expect(test.bootstraps[0]!.environment).toMatchObject({
      GRADIATED_NOMAD_NODE_ID: BOUND_NODE,
      GRADIATED_NOMAD_NODE_SECRET: "3f1e5a52-8d4b-4c1e-9a55-222222222222",
    });
  });

  it("resumes a running machine that carries this instance's bootstrap without resetting it", async () => {
    const test = setup({
      stopped: false,
      machineEnvironment: carriedEnvironment,
      nodeAlreadyJoined: true,
    });

    const started = await test.registrations.start(request);
    const finished = await settled(test.registrations, started.id);

    expect(started.resuming).toBe(true);
    expect(finished).toMatchObject({ phase: "bound", nomadNodeId: BOUND_NODE });
    expect(test.bootstraps).toEqual([]);
    expect(test.bindNomadNode).toHaveBeenCalledWith(INSTANCE_ID, BOUND_NODE);
    expect(test.audit.mock.calls.map(([event]) => event.phase)).toEqual([
      "recording",
      "waiting_for_node",
      "bound",
    ]);
  });

  it("refuses to pretend an already registered machine was renewed", async () => {
    const test = setup({
      stopped: false,
      boundNodeId: BOUND_NODE,
      machineEnvironment: carriedEnvironment,
      nodeAlreadyJoined: true,
    });

    const finished = await settled(
      test.registrations,
      (await test.registrations.start(request)).id,
    );

    expect(finished).toMatchObject({
      phase: "failed",
      error: expect.stringContaining("is already registered"),
    });
    expect(test.bootstraps).toEqual([]);
    expect(test.bindNomadNode).not.toHaveBeenCalled();
  });

  it("will not resume a machine carrying another instance's bootstrap", async () => {
    const test = setup({
      stopped: false,
      machineEnvironment: {
        ...carriedEnvironment,
        GRADIATED_INSTANCE_ID: "019d5a4a-0000-7000-8000-000000000002",
      },
    });

    const finished = await settled(
      test.registrations,
      (await test.registrations.start(request)).id,
    );

    expect(finished).toMatchObject({
      phase: "failed",
      error: expect.stringContaining("carries the bootstrap of instance"),
    });
    expect(test.bootstraps).toEqual([]);
    expect(test.bindNomadNode).not.toHaveBeenCalled();
  });

  it("resets a bootstrapped machine only when asked, keeping its node", async () => {
    const test = setup({
      stopped: false,
      machineEnvironment: carriedEnvironment,
    });

    const started = await test.registrations.start({
      ...request,
      resetRunningPod: true,
    });
    await settled(test.registrations, started.id);

    expect(started.resuming).toBe(false);
    expect(test.bootstraps[0]).toMatchObject({
      environment: { GRADIATED_NOMAD_NODE_ID: BOUND_NODE },
      options: { allowReset: true },
    });
  });

  it("refuses a running machine without an authorized reset before touching anything", async () => {
    const test = setup({ stopped: false });

    await expect(test.registrations.start(request)).rejects.toThrow(
      "reset_running_pod",
    );
    expect(test.register).not.toHaveBeenCalled();
    expect(test.bootstraps).toEqual([]);
    expect(test.registrations.list()).toEqual([]);
  });

  it("resets a running machine when the reset is authorized", async () => {
    const test = setup({ stopped: false });

    const finished = await settled(
      test.registrations,
      (await test.registrations.start({ ...request, resetRunningPod: true }))
        .id,
    );

    expect(finished.phase).toBe("bound");
    expect(test.bootstraps[0]?.options).toEqual({ allowReset: true });
    expect(test.audit).toHaveBeenCalledWith(
      expect.objectContaining({ reset_running_pod: true, phase: "recording" }),
    );
  });

  it("allows one registration per machine at a time", async () => {
    const test = setup();

    const first = await test.registrations.start(request);

    await expect(test.registrations.start(request)).rejects.toThrow(
      `Registration ${first.id} for this machine is still`,
    );
    await settled(test.registrations, first.id);
  });

  it("lets only one of two simultaneous requests for a machine start", async () => {
    const test = setup();

    const results = await Promise.allSettled([
      test.registrations.start(request),
      test.registrations.start(request),
    ]);

    expect(results.map((result) => result.status).sort()).toEqual([
      "fulfilled",
      "rejected",
    ]);
    expect(
      results.find((result) => result.status === "rejected"),
    ).toMatchObject({
      reason: new Error("Another registration for this machine is starting"),
    });
    await settled(test.registrations, test.registrations.list()[0]!.id);
    expect(test.bootstraps).toHaveLength(1);
  });

  it("releases the machine when a request is refused", async () => {
    const test = setup({ stopped: false });

    await expect(test.registrations.start(request)).rejects.toThrow(
      "reset_running_pod",
    );

    await expect(
      test.registrations.start({ ...request, resetRunningPod: true }),
    ).resolves.toMatchObject({ phase: "recording" });
  });

  it("fails without binding when the node never becomes ready", async () => {
    const test = setup({ nodeStatus: "initializing" });

    const finished = await settled(
      test.registrations,
      (await test.registrations.start(request)).id,
    );

    expect(finished).toMatchObject({
      phase: "failed",
      error: expect.stringContaining("was not ready"),
    });
    expect(test.bindNomadNode).not.toHaveBeenCalled();
    expect(test.audit).toHaveBeenLastCalledWith(
      expect.objectContaining({ phase: "failed", error: finished.error }),
    );
  });

  it("rejects an unknown provider", async () => {
    await expect(
      setup().registrations.start({ ...request, provider: "aws" }),
    ).rejects.toThrow("Unknown provider aws");
  });
});
