export const queryKeys = {
  me: ["me"],
  workspaces: (organizationId: string) => ["workspaces", organizationId],
  members: (organizationId: string) => ["members", organizationId],
  invitations: (organizationId: string) => ["invitations", organizationId],
} as const;
