import { analytics } from "@/lib/analytics";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { format } from "date-fns";
import {
  CalendarIcon,
  KeyRound,
  LoaderCircle,
  MoreHorizontal,
  Plus,
} from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import {
  apiKeysQuery,
  revokeApiKey,
  useCreateApiKey,
  type CreatedApiKey,
} from "@/api/queries";
import { CopyStateIcon } from "@/components/copy-state-icon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { copyLabel, useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { useProductContext } from "@/hooks/use-product-context";
import { canManageOrganization } from "@/lib/roles";
import { errorMessage } from "@/lib/errors";
import {
  apiKeyExpiresAt,
  apiKeyStatus,
  firstSelectableExpiry,
  type ApiKeyStatus,
} from "@/pages/api-key-status";
import { ConsolePage, LoadFailed } from "@/pages/console-page";
import { OptionSelect } from "@/components/option-select";

const STATUS_BADGE: Record<
  ApiKeyStatus,
  { label: string; className: string; dotClassName: string | null }
> = {
  active: {
    label: "Active",
    className: "border-emerald-200 bg-emerald-50 text-emerald-700",
    dotClassName: "bg-emerald-500",
  },
  expired: {
    label: "Expired",
    className: "border-amber-200 bg-amber-50 text-amber-800",
    dotClassName: null,
  },
  revoked: {
    label: "Revoked",
    className: "text-muted-foreground",
    dotClassName: null,
  },
};

const STATUS_OPTIONS = (["active", "expired", "revoked"] as const).map(
  (value) => ({ value, label: STATUS_BADGE[value].label }),
);

const EMPTY_STATE: Record<ApiKeyStatus, { title: string; body: string }> = {
  active: {
    title: "No active API keys",
    body: "Create a key for this workspace when you are ready to send your first inference request.",
  },
  expired: {
    title: "No expired API keys",
    body: "Keys past their expiry date will appear here.",
  },
  revoked: {
    title: "No revoked API keys",
    body: "Revoked keys will appear here.",
  },
};

const keyDate = new Intl.DateTimeFormat(undefined, {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const formatDate = (value: string) => keyDate.format(new Date(value));

export const ApiKeysPage = () => {
  const queryClient = useQueryClient();
  const { user, organizationId, workspaceId, selectedOrganization } =
    useProductContext();
  const canManage = canManageOrganization(selectedOrganization);
  const [createOpen, setCreateOpen] = useState(false);
  const [created, setCreated] = useState<CreatedApiKey | null>(null);
  const secretCopy = useCopyToClipboard();
  const [statusFilter, setStatusFilter] = useState<ApiKeyStatus>("active");

  const keysQuery = apiKeysQuery(organizationId, workspaceId);
  const keys = useQuery(keysQuery);

  const revoke = useMutation({
    mutationFn: (apiKeyId: string) =>
      revokeApiKey(organizationId, workspaceId, apiKeyId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: keysQuery.queryKey }),
  });

  const now = new Date();
  const filteredKeys = (keys.data?.data ?? []).flatMap((apiKey) => {
    const status = apiKeyStatus(apiKey, now);

    return status === statusFilter ? [{ apiKey, status }] : [];
  });
  const emptyState = EMPTY_STATE[statusFilter];

  return (
    <ConsolePage
      page="api-keys"
      title="API keys"
      description="Create an API key to call models from your agents."
      actions={
        <>
          <OptionSelect
            value={statusFilter}
            options={STATUS_OPTIONS}
            onValueChange={setStatusFilter}
            label="Key status"
            className="h-9 min-w-32"
          />
          <CreateKeyDialog
            open={createOpen}
            onOpenChange={(open) => {
              if (open)
                analytics.track("api_key_create_clicked", {
                  organization_id: organizationId,
                  workspace_id: workspaceId,
                });
              setCreateOpen(open);
            }}
            organizationId={organizationId}
            workspaceId={workspaceId}
            disabled={!workspaceId}
            onCreated={(result) => {
              setCreated(result);
              setCreateOpen(false);
            }}
          />
        </>
      }
    >
      {revoke.isError ? (
        <div
          role="alert"
          className="mb-4 rounded-lg border border-destructive/25 bg-destructive/5 px-4 py-3 text-sm text-destructive"
        >
          {errorMessage(revoke.error, "The API key could not be revoked.")}
        </div>
      ) : null}

      <section className="overflow-hidden rounded-lg border bg-card">
        {keys.isLoading ? (
          <div className="grid min-h-48 place-items-center">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : keys.isError ? (
          <LoadFailed
            subject="API keys"
            retrying={keys.isFetching}
            onRetry={() => void keys.refetch()}
          />
        ) : filteredKeys.length ? (
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-11 pl-5">Name</TableHead>
                <TableHead className="h-11 px-4">Created</TableHead>
                <TableHead className="h-11 px-4">Expires</TableHead>
                <TableHead className="h-11 px-4">Status</TableHead>
                <TableHead className="h-11 w-14 pr-3 text-right">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredKeys.map(({ apiKey, status }) => (
                <TableRow key={apiKey.id}>
                  <TableCell className="h-16 pl-5 font-medium">
                    {apiKey.name}
                  </TableCell>
                  <TableCell className="px-4 text-muted-foreground">
                    {formatDate(apiKey.created_at)}
                  </TableCell>
                  <TableCell className="px-4 text-muted-foreground">
                    {apiKey.expires_at
                      ? formatDate(apiKey.expires_at)
                      : "Never"}
                  </TableCell>
                  <TableCell className="px-4">
                    <StatusBadge status={status} />
                  </TableCell>
                  <TableCell className="pr-3 text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Actions for ${apiKey.name}`}
                        >
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-36">
                        <DropdownMenuItem asChild>
                          <Link to="/logs" search={{ apiKeyId: apiKey.id }}>
                            View logs
                          </Link>
                        </DropdownMenuItem>
                        {status !== "revoked" ? (
                          <DropdownMenuItem
                            disabled={
                              revoke.isPending ||
                              (!canManage && apiKey.created_by !== user?.id)
                            }
                            className="text-destructive focus:text-destructive"
                            onSelect={() => {
                              if (
                                window.confirm(
                                  `Revoke ${apiKey.name}? This cannot be undone.`,
                                )
                              ) {
                                revoke.mutate(apiKey.id);
                              }
                            }}
                          >
                            Revoke
                          </DropdownMenuItem>
                        ) : null}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="flex min-h-56 flex-col items-center justify-center px-6 text-center">
            <div className="mb-4 grid size-11 place-items-center rounded-lg bg-muted">
              <KeyRound className="size-5 text-muted-foreground" />
            </div>
            <h3 className="font-medium">{emptyState.title}</h3>
            <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">
              {emptyState.body}
            </p>
          </div>
        )}
      </section>

      <Dialog
        open={Boolean(created)}
        onOpenChange={(open) => !open && setCreated(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Copy your API key</DialogTitle>
            <DialogDescription>
              This is the only time the secret will be displayed. Store it in a
              secure password manager or secret store.
            </DialogDescription>
          </DialogHeader>
          <div
            className="ph-no-capture rounded-lg border bg-muted p-3 font-mono text-xs leading-5 break-all"
            data-testid="api-key-secret"
          >
            {created?.secret}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                if (!created) return;
                analytics.track("api_key_copy_clicked", {
                  organization_id: organizationId,
                  workspace_id: workspaceId,
                  api_key_id: created.api_key.id,
                });
                void secretCopy.copy(created.secret);
              }}
            >
              <CopyStateIcon state={secretCopy.state} className="size-4" />
              {copyLabel(secretCopy.state, "Copy key")}
            </Button>
            <Button onClick={() => setCreated(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ConsolePage>
  );
};

const StatusBadge = ({ status }: { status: ApiKeyStatus }) => {
  const { label, className, dotClassName } = STATUS_BADGE[status];

  return (
    <Badge variant="outline" className={className}>
      {dotClassName ? (
        <span className={`size-1.5 rounded-full ${dotClassName}`} />
      ) : null}
      {label}
    </Badge>
  );
};

const CreateKeyDialog = ({
  open,
  onOpenChange,
  organizationId,
  workspaceId,
  disabled,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  organizationId: string;
  workspaceId: string;
  disabled: boolean;
  onCreated: (result: CreatedApiKey) => void;
}) => {
  const [expiryOpen, setExpiryOpen] = useState(false);
  const form = useForm<CreateKeyValues>({
    resolver: zodResolver(CreateKeySchema),
    defaultValues: { name: "", expiresAt: undefined },
  });
  const mutation = useCreateApiKey(organizationId, workspaceId);

  const submit = (values: CreateKeyValues) =>
    mutation.mutate(
      {
        name: values.name,
        expires_at: values.expiresAt ? apiKeyExpiresAt(values.expiresAt) : null,
      },
      {
        onSuccess: (result) => {
          form.reset();
          onCreated(result);
        },
        onError: (error) =>
          form.setError("root", {
            message: errorMessage(error, "The API key could not be created."),
          }),
      },
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button disabled={disabled}>
          <Plus className="size-4" />
          Create API key
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={form.handleSubmit(submit)} className="space-y-5">
          <DialogHeader>
            <DialogTitle>Create API key</DialogTitle>
            <DialogDescription>
              The key belongs to the selected workspace. Its secret is shown
              once after creation.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="key-name">Name</Label>
            <Input
              id="key-name"
              autoComplete="off"
              data-1p-ignore="true"
              placeholder="Production"
              maxLength={200}
              autoFocus
              {...form.register("name")}
            />
            {form.formState.errors.name?.message ? (
              <p className="text-xs text-destructive">
                {form.formState.errors.name.message}
              </p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label>Expiry (optional)</Label>
            <Controller
              control={form.control}
              name="expiresAt"
              render={({ field }) => {
                const firstExpiry = firstSelectableExpiry(new Date());

                return (
                  <Popover open={expiryOpen} onOpenChange={setExpiryOpen}>
                    <PopoverTrigger asChild>
                      <Button
                        type="button"
                        variant="outline"
                        aria-label="Expiry date"
                        className="w-full justify-start text-left font-normal"
                      >
                        <CalendarIcon className="size-4 text-muted-foreground" />
                        {field.value ? (
                          format(field.value, "PPP")
                        ) : (
                          <span className="text-muted-foreground">
                            Never expires
                          </span>
                        )}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={field.value}
                        disabled={{ before: firstExpiry }}
                        onSelect={(date) => {
                          field.onChange(date);
                          if (date) setExpiryOpen(false);
                        }}
                        autoFocus
                      />
                      {field.value ? (
                        <div className="border-t p-2">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="w-full"
                            onClick={() => {
                              field.onChange(undefined);
                              setExpiryOpen(false);
                            }}
                          >
                            Clear expiry
                          </Button>
                        </div>
                      ) : null}
                    </PopoverContent>
                  </Popover>
                );
              }}
            />
          </div>
          {form.formState.errors.root?.message ? (
            <p role="alert" className="text-sm text-destructive">
              {form.formState.errors.root.message}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : null}
              Create key
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

const CreateKeySchema = z.object({
  name: z.string().trim().min(1, "Enter a name.").max(200),
  expiresAt: z.date().optional(),
});

type CreateKeyValues = z.infer<typeof CreateKeySchema>;
