import { randomUUID } from "node:crypto";

import type { InstanceService } from "@gradiated/control";

import {
  hostProfile,
  issueCertificate,
  type CertificateSigner,
} from "@gradiated/nomad-pki";
import {
  carriedBootstrap,
  hostBootstrapEnvironment,
  nodeName,
  nomadNodeIdentity,
  servingEnvironment,
  type ArtifactCredentials,
} from "./host-bootstrap.js";
import { waitForNomadNode, type ReadNomadNode } from "./nomad-node.js";
import type { InstanceProvider, ProviderInstance } from "./provider.js";

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
  readonly resuming: boolean;
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
  readonly hostImage: string;
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
      resuming: registration.resuming,
      requested_by: registration.requestedBy,
      ...(registration.error && phase === "failed"
        ? { error: registration.error }
        : {}),
    });
  };

  const waitAndBind = async (instanceId: string, nomadNodeId: string) => {
    await waitForNomadNode(dependencies.readNode, {
      nomadNodeId,
      instanceId,
      timeoutMs: dependencies.nodeTimeoutMs ?? NODE_READY_TIMEOUT_MS,
    });
    await (
      await dependencies.instances()
    ).bindNomadNode(instanceId, nomadNodeId);
  };

  const run = async (
    registration: Registration,
    provider: InstanceProvider,
    instance: ProviderInstance,
    environment: Readonly<Record<string, string>>,
  ) => {
    const record = await (await dependencies.instances()).register(instance);
    const name = nodeName(instance.provider, instance.providerInstanceId);

    const carried = carriedBootstrap(environment);
    if (registration.resuming && carried) {
      if (carried.instanceId !== record.id) {
        throw new Error(
          `${registration.providerInstanceId} carries the bootstrap of instance ${carried.instanceId}, not ${record.id}; ` +
            "register it again with an authorized reset",
        );
      }
      if (record.nomadNodeId === carried.nomadNodeId) {
        throw new Error(
          `${registration.providerInstanceId} is already registered as node ${carried.nomadNodeId}; ` +
            "renewing its certificate or image needs reset_running_pod",
        );
      }

      advance(registration, "waiting_for_node", {
        instanceId: record.id,
        nomadNodeId: carried.nomadNodeId,
        nodeName: name,
      });
      await waitAndBind(record.id, carried.nomadNodeId);
      advance(registration, "bound");

      return;
    }

    const [ca, artifact, tokens] = await Promise.all([
      dependencies.caCertificate(),
      dependencies.runtimeReader(),
      dependencies.servingTokens(registration.provider),
    ]);
    const identity = nomadNodeIdentity(record.id, environment);
    advance(registration, "issuing_certificate", {
      instanceId: record.id,
      nomadNodeId: identity.nomadNodeId,
      nodeName: name,
    });

    const tls = await issueCertificate(ca, dependencies.signer, hostProfile);
    advance(registration, "updating_provider");

    await provider.bootstrap(
      instance,
      dependencies.hostImage,
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

    await waitAndBind(record.id, identity.nomadNodeId);
    advance(registration, "bound");
  };

  // A running machine that already carries our bootstrap is resumed: it is
  // waited for and bound, never reset, unless a reset is explicitly requested.
  const preflight = async (
    createProvider: () => Promise<InstanceProvider>,
    request: RegistrationRequest,
  ) => {
    const provider = await createProvider();
    const instance = await provider.describe(request.providerInstanceId);
    const stopped = await provider.isStopped(request.providerInstanceId);
    const environment = await provider.environment(request.providerInstanceId);
    const resuming =
      !stopped &&
      !request.resetRunningPod &&
      carriedBootstrap(environment) !== null;

    if (!stopped && !request.resetRunningPod && !resuming) {
      throw new Error(
        `${instance.sku} ${request.providerInstanceId} is running or has an unknown status. ` +
          "Registering it resets the machine, which can release scarce GPU capacity. " +
          "Only when that reset is explicitly authorized, call again with " +
          "reset_running_pod true and the same id in confirm_instance_id.",
      );
    }

    return { provider, instance, environment, resuming };
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
        const { provider, instance, environment, resuming } = await preflight(
          createProvider,
          request,
        );
        const now = new Date().toISOString();
        const registration: Registration = {
          id: randomUUID(),
          provider: request.provider,
          providerInstanceId: request.providerInstanceId,
          sku: instance.sku,
          requestedBy: request.requestedBy,
          resetRunningPod: request.resetRunningPod,
          resuming,
          startedAt: now,
          updatedAt: now,
          phase: "recording",
        };
        retain(registration);
        advance(registration, "recording");

        void run(registration, provider, instance, environment).catch(
          (error: unknown) =>
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
