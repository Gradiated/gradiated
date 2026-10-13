import type { InstanceRegistration } from "@gradiated/control";

export type ProviderInstance = InstanceRegistration;

export interface HostImage {
  readonly reference: string;
  readonly registry: { username: string; password: string } | null;
}

export type GpuInventory = {
  tailscaleIp: string;
  gpuCount: number;
  gpuProduct: string;
  cpu: number;
  memoryGiB: number;
};

export interface InstanceProvider {
  describe(providerInstanceId: string): Promise<ProviderInstance>;
  environment(
    providerInstanceId: string,
    options?: { readonly providerOnly?: boolean },
  ): Promise<Record<string, string>>;
  isStopped(providerInstanceId: string): Promise<boolean>;
  supportsInPlace?(providerInstanceId: string, image: string): Promise<boolean>;
  checkTailscaleEnrollment(providerInstanceId: string): Promise<void>;
  bootstrap(
    instance: ProviderInstance,
    image: string,
    environment: Readonly<Record<string, string>>,
    options?: { readonly allowReset?: boolean },
  ): Promise<GpuInventory>;
}
