import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId } from "react";
import { toast } from "sonner";

import { updateOrganization, type CurrentUser } from "@/api/queries";
import type { components } from "@/api/schema";
import { Switch } from "@/components/ui/switch";
import { useProductContext } from "@/hooks/use-product-context";
import { queryKeys } from "@/lib/query-keys";
import { canManageOrganization } from "@/lib/roles";
import { NameSetting } from "./name-setting";
import { SettingsHeader } from "./settings-layout";

export const OrganizationSettingsPage = () => {
  const { user, organizationId, selectedOrganization } = useProductContext();
  const client = useQueryClient();
  const canEdit = canManageOrganization(selectedOrganization);

  const save = async (patch: components["schemas"]["UpdateOrganization"]) => {
    const updated = await updateOrganization(organizationId, patch);
    client.setQueryData<CurrentUser>(
      queryKeys.me,
      (current) =>
        current && {
          ...current,
          organizations: current.organizations.map((row) =>
            row.id === updated.id ? updated : row,
          ),
        },
    );
  };

  return (
    <>
      <SettingsHeader
        title="Organization"
        description="Settings shared by every workspace in this organization."
      />
      {selectedOrganization ? (
        <div className="space-y-4">
          <NameSetting
            key={`${selectedOrganization.id}:${selectedOrganization.name}`}
            label="Organization name"
            savedName={selectedOrganization.name}
            canEdit={canEdit}
            onSave={(name) => save({ name })}
            successMessage="Organization renamed."
          />
          <AutoJoinSetting
            organizationName={selectedOrganization.name}
            domain={
              selectedOrganization.auto_join_domain ??
              user?.company_email_domain ??
              null
            }
            enabled={selectedOrganization.auto_join_domain !== null}
            canEdit={canEdit}
            onSave={(domain) => save({ auto_join_domain: domain })}
          />
        </div>
      ) : (
        <p role="status">Loading organization settings…</p>
      )}
    </>
  );
};

const AutoJoinSetting = ({
  organizationName,
  domain,
  enabled,
  canEdit,
  onSave,
}: {
  organizationName: string;
  domain: string | null;
  enabled: boolean;
  canEdit: boolean;
  onSave: (domain: string | null) => Promise<void>;
}) => {
  const id = useId();
  const save = useMutation({
    mutationFn: onSave,
    onSuccess: (_, saved) =>
      toast.success(
        saved
          ? "Automatic joining turned on."
          : "Automatic joining turned off.",
      ),
    onError: (error) => toast.error(error.message),
  });

  if (!domain) return null;

  return (
    <div className="flex max-w-xl items-center gap-6 rounded-xl border bg-card p-6">
      <div className="min-w-0 flex-1">
        <label htmlFor={id} className="text-sm font-medium">
          Anyone with an{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
            @{domain}
          </code>{" "}
          email can join
        </label>
        <p className="mt-1 text-sm leading-5 text-muted-foreground">
          Let teammates join {organizationName} without an invite when they sign
          in with a verified company email.
        </p>
      </div>
      <Switch
        id={id}
        checked={save.isPending ? save.variables !== null : enabled}
        onCheckedChange={(checked) => save.mutate(checked ? domain : null)}
        disabled={!canEdit || save.isPending}
      />
    </div>
  );
};
