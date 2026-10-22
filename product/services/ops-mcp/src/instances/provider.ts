import type { InstanceRegistration } from "@gradiated/control";

import type { EnrollmentPayload, EnrollmentResult } from "@gradiated/gpu-hosts";

export type ProviderInstance = InstanceRegistration;

// What enrollment measured, with the address the host serves from after promotion.
export type GpuInventory = Omit<EnrollmentResult, "version" | "promotion">;

export interface InstanceProvider {
  describe(providerInstanceId: string): Promise<ProviderInstance>;
  isStopped(providerInstanceId: string): Promise<boolean>;
  supportsInPlace?(providerInstanceId: string, image: string): Promise<boolean>;
  checkTailscaleEnrollment(
    providerInstanceId: string,
    options?: { readonly allowReset?: boolean },
  ): Promise<void>;
  bootstrap(
    instance: ProviderInstance,
    image: string,
    payload: EnrollmentPayload,
    options?: { readonly allowReset?: boolean },
  ): Promise<GpuInventory>;
}
