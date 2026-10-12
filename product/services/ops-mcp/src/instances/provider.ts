import type { InstanceRegistration } from "@gradiated/control";

export type ProviderInstance = InstanceRegistration;

export interface HostImage {
  readonly reference: string;
  readonly registry: { username: string; password: string } | null;
}

export interface InstanceProvider {
  describe(providerInstanceId: string): Promise<ProviderInstance>;
  environment(
    providerInstanceId: string,
    options?: { readonly providerOnly?: boolean },
  ): Promise<Record<string, string>>;
  isStopped(providerInstanceId: string): Promise<boolean>;
  supportsInPlace?(providerInstanceId: string, image: string): Promise<boolean>;
  resume?(providerInstanceId: string): Promise<void>;
  checkTailscaleEnrollment(providerInstanceId: string): Promise<void>;
  enrollTailscale(
    providerInstanceId: string,
    instanceId: string,
    authKey: string,
  ): Promise<{ tailscaleIp: string }>;
  bootstrap(
    instance: ProviderInstance,
    image: string,
    environment: Readonly<Record<string, string>>,
    options?: { readonly allowReset?: boolean },
  ): Promise<void>;
}
