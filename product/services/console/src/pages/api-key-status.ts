import type { ApiKey } from "@/api/queries";

export type ApiKeyStatus = "active" | "expired" | "revoked";

export const apiKeyStatus = (
  apiKey: Pick<ApiKey, "expires_at" | "revoked_at">,
  now: Date,
): ApiKeyStatus => {
  if (apiKey.revoked_at) return "revoked";

  const expired =
    apiKey.expires_at !== null &&
    new Date(apiKey.expires_at).getTime() <= now.getTime();

  return expired ? "expired" : "active";
};

export const apiKeyExpiresAt = (day: Date): string =>
  new Date(
    Date.UTC(day.getFullYear(), day.getMonth(), day.getDate(), 23, 59, 59, 999),
  ).toISOString();

export const firstSelectableExpiry = (now: Date): Date => {
  const tomorrow = new Date(now);
  tomorrow.setHours(0, 0, 0, 0);
  tomorrow.setDate(tomorrow.getDate() + 1);

  return tomorrow;
};
