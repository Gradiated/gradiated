import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateWorkspace, type UpdateWorkspace } from "@/api/queries";
import { useProductContext } from "@/hooks/use-product-context";
import { queryKeys } from "@/lib/query-keys";
import { Switch } from "@/components/ui/switch";
import { SettingRow } from "./settings-card";

export const TraceCaptureSettings = () => {
  const { organizationId, workspaceId, workspaces, selectedOrganization } =
    useProductContext();
  const workspace = workspaces.find((row) => row.id === workspaceId);
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (settings: UpdateWorkspace) =>
      updateWorkspace(organizationId, workspaceId, settings),
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: queryKeys.workspaces(organizationId),
      }),
  });
  const enabled =
    selectedOrganization &&
    ["owner", "admin"].includes(selectedOrganization.role) &&
    selectedOrganization.status === "active";
  if (!workspace) return null;
  const change = (settings: UpdateWorkspace) => save.mutate(settings);
  return (
    <>
      <SettingRow
        title="Trace capture"
        description="Store requests with a task header. Relayed content is not used for automatic training. Changes take effect within 15 seconds."
      >
        <Switch
          checked={workspace.trace_capture_enabled}
          disabled={!enabled || save.isPending}
          onCheckedChange={(trace_capture_enabled) =>
            change({ trace_capture_enabled })
          }
          aria-label="Trace capture"
        />
      </SettingRow>
      <SettingRow
        title="Content retention"
        description="Applies to new captures. Existing content keeps the retention chosen when it was captured."
      >
        <select
          aria-label="Content retention"
          className="rounded-md border bg-background px-3 py-2 text-sm"
          value={workspace.trace_retention_days}
          disabled={!enabled || save.isPending}
          onChange={(event) =>
            change({
              trace_retention_days: Number(event.target.value) as 30 | 90 | 180,
            })
          }
        >
          {[30, 90, 180].map((days) => (
            <option key={days} value={days}>
              {days} days
            </option>
          ))}
        </select>
      </SettingRow>
      {save.error ? (
        <p role="alert" className="p-4 text-sm text-destructive">
          Could not save capture settings. {save.error.message}
        </p>
      ) : null}
    </>
  );
};
