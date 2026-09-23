export const queryKeys = {
  me: ["me"],
  workspaces: (organizationId: string) => ["workspaces", organizationId],
} as const;
