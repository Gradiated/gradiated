export const INVITATION_TOKEN = /^[A-Za-z0-9_-]{43}$/;

export interface LoginSearch {
  invitation?: string;
}

export const parseLoginSearch = (
  search: Record<string, unknown>,
): LoginSearch =>
  typeof search.invitation === "string" &&
  INVITATION_TOKEN.test(search.invitation)
    ? { invitation: search.invitation }
    : {};

export const invitationPath = (token: string) =>
  `/invitations/accept?token=${token}`;
