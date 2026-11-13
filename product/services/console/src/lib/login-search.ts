import { isOAuthPath } from "@/lib/oauth";

export const POST_TRAINING_JOURNEY = "post-training";

export const INVITATION_TOKEN = /^[A-Za-z0-9_-]{43}$/;

export interface LoginSearch {
  invitation?: string;
  journey?: typeof POST_TRAINING_JOURNEY;
  // An OAuth authorization to return to after sign-in.
  next?: string;
}

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
  ...(typeof search.next === "string" && isOAuthPath(search.next)
    ? { next: search.next }
    : {}),
});

export const invitationPath = (token: string) =>
  `/invitations/accept?token=${token}`;
