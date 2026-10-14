import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { toast } from "sonner";

import {
  updateOrganization,
  updateWorkspace,
  type CurrentUser,
} from "@/api/queries";
import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { TabsContent } from "@/components/ui/tabs";
import { OptionTabs } from "@/components/option-select";
import { useProductContext } from "@/hooks/use-product-context";
import { queryKeys } from "@/lib/query-keys";
import { ConsolePage } from "./console-page";

type Scope = "workspace" | "organization";
const tabs = [
  { value: "workspace", label: "Workspace" },
  { value: "organization", label: "Organization" },
] as const;

export const SettingsPage = () => {
  const [tab, setTab] = useState<Scope>("workspace");
  const {
    user,
    organizationId,
    workspaceId,
    workspaces,
    selectedOrganization,
  } = useProductContext();
  const client = useQueryClient();
  const workspace = workspaces.find((row) => row.id === workspaceId);
  const canEdit =
    selectedOrganization?.status === "active" &&
    ["owner", "admin"].includes(selectedOrganization.role);

  const saveWorkspace = async (name: string) => {
    const updated = await updateWorkspace(organizationId, workspaceId, {
      name,
    });
    client.setQueryData<components["schemas"]["WorkspaceList"]>(
      queryKeys.workspaces(organizationId),
      (current) =>
        current && {
          ...current,
          data: current.data.map((row) =>
            row.id === updated.id ? updated : row,
          ),
        },
    );
  };
  const saveOrganization = async (
    patch: components["schemas"]["UpdateOrganization"],
  ) => {
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
    <ConsolePage page="settings" title="Settings">
      <OptionTabs value={tab} options={tabs} onValueChange={setTab}>
        <TabsContent value="workspace">
          {workspace ? (
            <NameSetting
              key={`${workspace.id}:${workspace.name}`}
              label="Workspace name"
              savedName={workspace.name}
              canEdit={canEdit}
              onSave={saveWorkspace}
              successMessage="Workspace renamed."
            />
          ) : (
            <p role="status">Loading workspace settings…</p>
          )}
        </TabsContent>
        <TabsContent value="organization">
          {selectedOrganization ? (
            <>
              <NameSetting
                key={`${selectedOrganization.id}:${selectedOrganization.name}`}
                label="Organization name"
                savedName={selectedOrganization.name}
                canEdit={canEdit}
                onSave={(name) => saveOrganization({ name })}
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
                onSave={(domain) =>
                  saveOrganization({ auto_join_domain: domain })
                }
              />
            </>
          ) : (
            <p role="status">Loading organization settings…</p>
          )}
        </TabsContent>
      </OptionTabs>
    </ConsolePage>
  );
};

const NameSetting = ({
  label,
  savedName,
  canEdit,
  onSave,
  successMessage,
}: {
  label: string;
  savedName: string;
  canEdit: boolean;
  onSave: (name: string) => Promise<void>;
  successMessage: string;
}) => {
  const id = useId();
  const [name, setName] = useState(savedName);
  const save = useMutation({
    mutationFn: onSave,
    onSuccess: () => toast.success(successMessage),
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (canEdit && name.trim() && name.trim() !== savedName && !save.isPending)
      save.mutate(name.trim());
  };

  return (
    <form
      className="mt-4 max-w-xl space-y-5 rounded-xl border bg-card p-6"
      onSubmit={submit}
    >
      <Field>
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        <Input
          id={id}
          name="scopeLabel"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={200}
          required
          autoComplete="off"
          data-1p-ignore="true"
          disabled={!canEdit || save.isPending}
        />
      </Field>
      {save.error ? (
        <p role="alert" className="text-sm text-destructive">
          {save.error.message}
        </p>
      ) : null}
      <Button
        type="submit"
        disabled={
          !canEdit ||
          save.isPending ||
          !name.trim() ||
          name.trim() === savedName
        }
      >
        {save.isPending ? "Saving…" : "Save changes"}
      </Button>
    </form>
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
    <div className="mt-4 flex max-w-xl items-center gap-6 rounded-xl border bg-card p-6">
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
