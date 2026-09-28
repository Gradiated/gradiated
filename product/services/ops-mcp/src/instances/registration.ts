import { randomUUID } from "node:crypto";

import type { InstanceService } from "@gradiated/control";

import {
  hostProfile,
  issueCertificate,
  type CertificateSigner,
} from "../nomad-certificates.js";
import {
  hostBootstrapEnvironment,
  nodeName,
  nomadNodeIdentity,
  servingEnvironment,
  type ArtifactCredentials,
} from "./host-bootstrap.js";
import { waitForNomadNode, type ReadNomadNode } from "./nomad-node.js";
import type {
  HostImage,
  InstanceProvider,
  ProviderInstance,
} from "./provider.js";

const NODE_READY_TIMEOUT_MS = 30 * 60 * 1000;
const RETAINED_REGISTRATIONS = 50;

export type RegistrationPhase =
  | "recording"
  | "issuing_certificate"
  | "updating_provider"
  | "waiting_for_node"
  | "bound"
  | "failed";

export type Registration = {
  readonly id: string;
  readonly provider: string;
  readonly providerInstanceId: string;
  readonly sku: string;
  readonly requestedBy: string;
  readonly resetRunningPod: boolean;
  readonly startedAt: string;
  phase: RegistrationPhase;
  updatedAt: string;
  instanceId?: string;
  nomadNodeId?: string;
  nodeName?: string;
  error?: string;
};

export type RegistrationRequest = {
  readonly provider: string;
  readonly providerInstanceId: string;
  readonly resetRunningPod: boolean;
  readonly requestedBy: string;
};

export type RegistrationDependencies = {
  readonly providers: Readonly<Record<string, () => Promise<InstanceProvider>>>;
  readonly instances: () => Promise<InstanceService>;
  readonly hostImage: () => Promise<HostImage>;
  readonly caCertificate: () => Promise<string>;
  readonly signer: CertificateSigner;
  readonly runtimeReader: () => Promise<ArtifactCredentials>;
  readonly servingTokens: (provider: string) => Promise<{
    runtimeAccess: string;
    deploymentStatus: string;
  }>;
  readonly readNode: ReadNomadNode;
  readonly audit: (event: Record<string, unknown>) => void;
  readonly nodeTimeoutMs?: number;
};

export type Registrations = ReturnType<typeof createRegistrations>;

const isActive = ({ phase }: Registration) =>
  phase !== "bound" && phase !== "failed";

export const createRegistrations = (dependencies: RegistrationDependencies) => {
  const registrations = new Map<string, Registration>();
  const checking = new Set<string>();

  const advance = (
    registration: Registration,
    phase: RegistrationPhase,
    detail: Partial<Registration> = {},
  ) => {
    Object.assign(registration, detail, {
      phase,
      updatedAt: new Date().toISOString(),
    });
    dependencies.audit({
      event: "instance_registration",
      registration_id: registration.id,
      phase,
      provider: registration.provider,
      provider_instance_id: registration.providerInstanceId,
      reset_running_pod: registration.resetRunningPod,
      requested_by: registration.requestedBy,
      ...(registration.error && phase === "failed"
        ? { error: registration.error }
        : {}),
    });
  };

  const run = async (
    registration: Registration,
    provider: InstanceProvider,
    instance: ProviderInstance,
  ) => {
    const [image, ca, artifact, tokens] = await Promise.all([
      dependencies.hostImage(),
      dependencies.caCertificate(),
      dependencies.runtimeReader(),
      dependencies.servingTokens(registration.provider),
    ]);

    const record = await (await dependencies.instances()).register(instance);
    const identity = nomadNodeIdentity(
      record.nomadNodeId,
      await provider.environment(registration.providerInstanceId),
    );
    const name = nodeName(instance.provider, instance.providerInstanceId);
    advance(registration, "issuing_certificate", {
      instanceId: record.id,
      nomadNodeId: identity.nomadNodeId,
      nodeName: name,
    });

    const tls = await issueCertificate(ca, dependencies.signer, hostProfile);
    advance(registration, "updating_provider");

    await provider.bootstrap(
      instance,
      image,
      {
        ...hostBootstrapEnvironment({
          instanceId: record.id,
          nodeName: name,
          ...identity,
          ca,
          ...tls,
          artifact,
        }),
        ...servingEnvironment(tokens),
      },
      { allowReset: registration.resetRunningPod },
    );
    advance(registration, "waiting_for_node");

    await waitForNomadNode(dependencies.readNode, {
      nomadNodeId: identity.nomadNodeId,
      instanceId: record.id,
      timeoutMs: dependencies.nodeTimeoutMs ?? NODE_READY_TIMEOUT_MS,
    });
    await (
      await dependencies.instances()
    ).bindNomadNode(record.id, identity.nomadNodeId);
    advance(registration, "bound");
  };

  const preflight = async (
    createProvider: () => Promise<InstanceProvider>,
    request: RegistrationRequest,
  ) => {
    const provider = await createProvider();
    const instance = await provider.describe(request.providerInstanceId);
    if (
      !request.resetRunningPod &&
      !(await provider.isStopped(request.providerInstanceId))
    ) {
      throw new Error(
        `${instance.sku} ${request.providerInstanceId} is running or has an unknown status. ` +
          "Registering it resets the machine, which can release scarce GPU capacity. " +
          "Only when that reset is explicitly authorized, call again with " +
          "reset_running_pod true and the same id in confirm_instance_id.",
      );
    }

    return { provider, instance };
  };

  const retain = (registration: Registration) => {
    registrations.set(registration.id, registration);

    for (const [id, old] of registrations) {
      if (registrations.size <= RETAINED_REGISTRATIONS) break;
      if (!isActive(old)) registrations.delete(id);
    }
  };

  return {
    async start(request: RegistrationRequest): Promise<Registration> {
      const createProvider = dependencies.providers[request.provider];
      if (!createProvider) {
        throw new Error(`Unknown provider ${request.provider}`);
      }

      const machine = `${request.provider}/${request.providerInstanceId}`;
      const running = [...registrations.values()].find(
        (registration) =>
          isActive(registration) &&
          registration.provider === request.provider &&
          registration.providerInstanceId === request.providerInstanceId,
      );
      if (running) {
        throw new Error(
          `Registration ${running.id} for this machine is still ${running.phase}`,
        );
      }
      if (checking.has(machine)) {
        throw new Error("Another registration for this machine is starting");
      }

      checking.add(machine);
      try {
        const { provider, instance } = await preflight(createProvider, request);
        const now = new Date().toISOString();
        const registration: Registration = {
          id: randomUUID(),
          provider: request.provider,
          providerInstanceId: request.providerInstanceId,
          sku: instance.sku,
          requestedBy: request.requestedBy,
          resetRunningPod: request.resetRunningPod,
          startedAt: now,
          updatedAt: now,
          phase: "recording",
        };
        retain(registration);
        advance(registration, "recording");

        void run(registration, provider, instance).catch((error: unknown) =>
          advance(registration, "failed", {
            error: error instanceof Error ? error.message : String(error),
          }),
        );

        return { ...registration };
      } finally {
        checking.delete(machine);
      }
    },

    get: (id: string) => {
      const registration = registrations.get(id);

      return registration && { ...registration };
    },

    list: () =>
      [...registrations.values()]
        .reverse()
        .map((registration) => ({ ...registration })),
  };
};
