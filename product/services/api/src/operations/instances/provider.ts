import type { InstanceRegistration } from "@gradiated/control";

export type ProviderInstance = InstanceRegistration;

export interface HostImage {
  readonly reference: string;
  readonly registry: { username: string; password: string } | null;
}

export interface InstanceProvider {
  describe(providerInstanceId: string): Promise<ProviderInstance>;
  environment(providerInstanceId: string): Promise<Record<string, string>>;
  bootstrap(
    instance: ProviderInstance,
    image: HostImage,
    environment: Readonly<Record<string, string>>,
  ): Promise<void>;
}
