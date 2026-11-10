export const POST_TRAINING_JOURNEY = "post-training";

export const INVITATION_TOKEN = /^[A-Za-z0-9_-]{43}$/;

export interface LoginSearch {
  invitation?: string;
  journey?: typeof POST_TRAINING_JOURNEY;
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
});

export const invitationPath = (token: string) =>
  `/invitations/accept?token=${token}`;
