import { randomUUID } from "node:crypto";
import type { InstanceService } from "@gradiated/control";

import type { EnrollmentPayload } from "@gradiated/gpu-hosts";
import type {
  InstanceProvider,
  ProviderInstance,
  GpuInventory,
} from "./provider.js";

const RETAINED_REGISTRATIONS = 50;

export type RegistrationPhase =
  "recording" | "updating_provider" | "prepared" | "failed";

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
  nodeName?: string;
  error?: string;
  tailscaleIp?: string;
  kubernetes?: {
    // The GpuHost's spec.provider, as gpu-inference/hosts.yaml records it.
    provider: GpuHostProvider;
    inventory: GpuInventory;
    inventoryEntry: {
      instance_id: string;
      gpu_count: number;
      cpu: number;
      memory_gib: number;
      gpu_product: string;
      management_secret: { key: string; property?: string };
    };
  };
};

export type GpuHostProvider =
  | {
      name: "runpod";
      accountId: string;
      podId: string;
      machineId?: string;
    }
  | {
      name: "aws";
      accountId: string;
      region: string;
      availabilityZone: string;
      ec2InstanceId: string;
    };

// Providers record a host's fault domain as <provider>:<machine or zone>.
const faultDomainOf = (instance: ProviderInstance) => {
  const prefix = `${instance.provider}:`;
  return instance.faultDomain?.startsWith(prefix)
    ? instance.faultDomain.slice(prefix.length)
    : undefined;
};

export const gpuHostProvider = (
  instance: ProviderInstance,
): GpuHostProvider => {
  const domain = faultDomainOf(instance);
  if (instance.provider === "aws") {
    if (!instance.region || !domain)
      throw new Error(
        `EC2 instance ${instance.providerInstanceId} has no region or availability zone`,
      );
    return {
      name: "aws",
      accountId: instance.providerAccountId,
      region: instance.region,
      availabilityZone: domain,
      ec2InstanceId: instance.providerInstanceId,
    };
  }
  if (instance.provider === "runpod")
    return {
      name: "runpod",
      accountId: instance.providerAccountId,
      podId: instance.providerInstanceId,
      ...(domain ? { machineId: domain } : {}),
    };
  throw new Error(`GpuHost has no provider ${instance.provider}`);
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
  // The GPU base image every provider runs, unless hostImages names another.
  readonly hostImage: string;
  readonly hostImages?: Readonly<Record<string, string>>;
  readonly enrollmentPayload: (
    instance: ProviderInstance,
    instanceId: string,
    key: string,
    authKey: string,
  ) => Promise<EnrollmentPayload>;
  readonly managementKey: (
    instanceId: string,
  ) => Promise<{ key: string; secretId: string; property?: string }>;
  readonly tailscaleAuthKey: (instanceId: string) => Promise<{
    key: string;
    revoke: () => Promise<void>;
  }>;
  readonly audit: (event: Record<string, unknown>) => void;
};

export type Registrations = ReturnType<typeof createRegistrations>;

const isActive = ({ phase }: Registration) =>
  phase !== "prepared" && phase !== "failed";

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

  const hostImage = (provider: string) =>
    dependencies.hostImages?.[provider] ?? dependencies.hostImage;

  const run = async (
    registration: Registration,
    provider: InstanceProvider,
    instance: ProviderInstance,
  ) => {
    const record = await (await dependencies.instances()).register(instance);
    advance(registration, "updating_provider", {
      instanceId: record.id,
      nodeName: `gpu-${record.id}`,
    });
    const management = await dependencies.managementKey(record.id);
    const enrollment = await dependencies.tailscaleAuthKey(record.id);
    try {
      const payload = await dependencies.enrollmentPayload(
        instance,
        record.id,
        management.key,
        enrollment.key,
      );
      const inventory = await provider.bootstrap(
        instance,
        hostImage(registration.provider),
        payload,
        { allowReset: registration.resetRunningPod },
      );
      advance(registration, "prepared", {
        tailscaleIp: inventory.tailscale_ip,
        kubernetes: {
          provider: gpuHostProvider(instance),
          inventory,
          inventoryEntry: {
            instance_id: record.id,
            gpu_count: inventory.gpu_count,
            cpu: inventory.cpu,
            memory_gib: inventory.memory_gib,
            gpu_product: inventory.gpu_product,
            management_secret: {
              key: management.secretId,
              ...(management.property ? { property: management.property } : {}),
            },
          },
        },
      });
    } finally {
      await enrollment.revoke().catch(() =>
        dependencies.audit({
          event: "tailscale_auth_key_revocation_failed",
          instance_id: record.id,
        }),
      );
    }
  };

  const preflight = async (
    createProvider: () => Promise<InstanceProvider>,
    request: RegistrationRequest,
  ) => {
    const provider = await createProvider();
    const instance = await provider.describe(request.providerInstanceId);
    // Refuse a host the GpuHost manifest could not name before touching it.
    gpuHostProvider(instance);
    await provider.checkTailscaleEnrollment(request.providerInstanceId, {
      allowReset: request.resetRunningPod,
    });
    const stopped = await provider.isStopped(request.providerInstanceId);
    const resuming = false;
    const inPlace =
      !stopped &&
      !request.resetRunningPod &&
      (await provider.supportsInPlace?.(
        request.providerInstanceId,
        hostImage(request.provider),
      ));

    if (!stopped && !request.resetRunningPod && !resuming && !inPlace) {
      throw new Error(
        `${instance.sku} ${request.providerInstanceId} is running or has an unknown status. ` +
          "Registering it resets the machine, which can release scarce GPU capacity. " +
          "Enroll it in place over the tailnet (v5 GPU base image with a bootstrap key) to preserve its reservation, or only when that reset is explicitly authorized, call again with " +
          "reset_running_pod true and the same id in confirm_instance_id.",
      );
    }

    return { provider, instance, resuming };
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
        const { provider, instance, resuming } = await preflight(
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
