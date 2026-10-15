import type { CurrentUser, OrganizationRole } from "@/api/queries";

export const ROLE_OPTIONS = [
  { value: "admin", label: "Admin" },
  { value: "member", label: "Member" },
] as const satisfies readonly { value: OrganizationRole; label: string }[];

export const roleLabel = (role: OrganizationRole) =>
  ROLE_OPTIONS.find((option) => option.value === role)?.label ?? role;

export const canManageOrganization = (
  organization: CurrentUser["organizations"][number] | undefined,
) => organization?.status === "active" && organization.role === "admin";
