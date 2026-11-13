import { isOAuthPath } from "@/lib/oauth";

export const POST_TRAINING_JOURNEY = "post-training";

export const INVITATION_TOKEN = /^[A-Za-z0-9_-]{43}$/;

export interface LoginSearch {
  invitation?: string;
  journey?: typeof POST_TRAINING_JOURNEY;
  // The console page, or OAuth authorization, to return to after sign-in.
  next?: string;
}

const parse = (value: string, base: string) => {
  try {
    return new URL(value, base);
  } catch {
    return undefined;
  }
};

// A path that stays on whichever origin it resolves against, so not `//host`.
export const consoleUrl = (value: string) => {
  const url = parse(value, "https://console.invalid");
  const other = parse(value, "https://other.invalid");
  return url?.origin === "https://console.invalid" &&
    other?.origin === "https://other.invalid"
    ? url
    : undefined;
};

// Returned as given, not normalized, so a signed OAuth query keeps its encoding.
export const nextPath = (value: unknown): string | undefined => {
  if (
    typeof value !== "string" ||
    !value.startsWith("/") ||
    value.length > 2048
  )
    return undefined;
  const url = consoleUrl(value);
  if (
    !url ||
    url.pathname === "/login" ||
    url.pathname.startsWith("/onboarding")
  )
    return undefined;
  return value;
};

export const parseLoginSearch = (
  search: Record<string, unknown>,
): LoginSearch => ({
  ...(typeof search.invitation === "string" &&
  INVITATION_TOKEN.test(search.invitation)
    ? { invitation: search.invitation }
    : {}),
  ...(search.journey === POST_TRAINING_JOURNEY
    ? { journey: POST_TRAINING_JOURNEY }
    : {}),
  ...(nextPath(search.next) ? { next: search.next as string } : {}),
});

export const isOAuthNext = (search: LoginSearch) =>
  search.next !== undefined && isOAuthPath(search.next);

export const invitationPath = (token: string) =>
  `/invitations/accept?token=${token}`;
