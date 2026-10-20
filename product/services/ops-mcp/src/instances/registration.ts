import { randomUUID } from "node:crypto";
import type { InstanceService } from "@gradiated/control";
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
    inventory: GpuInventory;
    inventoryEntry: {
      instance_id: string;
      tailscale_ip: string;
      gpu_count: number;
      cpu: number;
      memory_gib: number;
      gpu_product: string;
      management_secret: { key: string; property?: string };
    };
  };
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
  readonly bootstrap: (
    instance: ProviderInstance,
    instanceId: string,
    key: string,
    authKey: string,
  ) => Promise<Record<string, string>>;
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
      const environment = await dependencies.bootstrap(
        instance,
        record.id,
        management.key,
        enrollment.key,
      );
      const inventory = await provider.bootstrap(
        instance,
        dependencies.hostImage,
        environment,
        { allowReset: registration.resetRunningPod },
      );
      advance(registration, "prepared", {
        tailscaleIp: inventory.tailscaleIp,
        kubernetes: {
          inventory,
          inventoryEntry: {
            instance_id: record.id,
            tailscale_ip: inventory.tailscaleIp,
            gpu_count: inventory.gpuCount,
            cpu: inventory.cpu,
            memory_gib: inventory.memoryGiB,
            gpu_product: inventory.gpuProduct,
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
    await provider.checkTailscaleEnrollment(request.providerInstanceId);
    const stopped = await provider.isStopped(request.providerInstanceId);
    const resuming = false;
    const inPlace =
      !stopped &&
      !request.resetRunningPod &&
      (await provider.supportsInPlace?.(
        request.providerInstanceId,
        dependencies.hostImage,
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
