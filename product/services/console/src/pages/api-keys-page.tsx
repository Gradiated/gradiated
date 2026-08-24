import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { format } from "date-fns";
import {
  CalendarIcon,
  Check,
  Copy,
  KeyRound,
  LoaderCircle,
  MoreHorizontal,
  Plus,
} from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import {
  createApiKey,
  listApiKeys,
  revokeApiKey,
  type CreatedApiKey,
} from "@/api/queries";
import { AppShell } from "@/components/app-shell";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useProductContext } from "@/hooks/use-product-context";

type KeyStatusFilter = "active" | "revoked";

const formatDate = (value: string) => {
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
};

export const ApiKeysPage = () => {
  const queryClient = useQueryClient();
  const {
    user,
    organizationId,
    workspaceId,
    selectOrganization,
    selectWorkspace,
    signOut,
    workspaces,
  } = useProductContext();
  const [createOpen, setCreateOpen] = useState(false);
  const [created, setCreated] = useState<CreatedApiKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [statusFilter, setStatusFilter] = useState<KeyStatusFilter>("active");

  const keys = useQuery({
    queryKey: ["api-keys", organizationId, workspaceId],
    queryFn: () => listApiKeys(organizationId, workspaceId),
    enabled: Boolean(organizationId && workspaceId),
  });

  const revoke = useMutation({
    mutationFn: (apiKeyId: string) =>
      revokeApiKey(organizationId, workspaceId, apiKeyId),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["api-keys", organizationId, workspaceId],
      }),
  });

  const copySecret = async () => {
    if (!created) return;
    await navigator.clipboard.writeText(created.secret);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1_500);
  };

  const filteredKeys =
    keys.data?.data.filter((apiKey) =>
      statusFilter === "revoked"
        ? Boolean(apiKey.revoked_at)
        : !apiKey.revoked_at,
    ) ?? [];

  return (
    <AppShell
      user={user}
      organizationId={organizationId}
      workspaces={workspaces}
      workspaceId={workspaceId}
      onSelectOrganization={selectOrganization}
      onSelectWorkspace={selectWorkspace}
      onSignOut={signOut}
      activePage="api-keys"
      pageTitle="API keys"
    >
      <main className="min-w-0 flex-1 px-5 py-8 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-5xl">
          <div className="mb-8 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
            <div>
              <h1 className="text-3xl font-semibold tracking-[-0.035em]">
                API keys
              </h1>
              <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
                Create an API key to call models from your agents.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Select
                value={statusFilter}
                onValueChange={(value) =>
                  setStatusFilter(value as KeyStatusFilter)
                }
              >
                <SelectTrigger className="h-9 min-w-32" aria-label="Key status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="revoked">Revoked</SelectItem>
                </SelectContent>
              </Select>
              <CreateKeyDialog
                open={createOpen}
                onOpenChange={setCreateOpen}
                organizationId={organizationId}
                workspaceId={workspaceId}
                disabled={!workspaceId}
                onCreated={(result) => {
                  setCreated(result);
                  setCreateOpen(false);
                  void queryClient.invalidateQueries({
                    queryKey: ["api-keys", organizationId, workspaceId],
                  });
                }}
              />
            </div>
          </div>

          <section className="overflow-hidden rounded-lg border bg-card">
            {keys.isLoading ? (
              <div className="grid min-h-48 place-items-center">
                <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
              </div>
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
                  {filteredKeys.map((apiKey) => (
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
                        <Badge
                          variant="outline"
                          className={
                            apiKey.revoked_at
                              ? "text-muted-foreground"
                              : "border-emerald-200 bg-emerald-50 text-emerald-700"
                          }
                        >
                          {apiKey.revoked_at ? null : (
                            <span className="size-1.5 rounded-full bg-emerald-500" />
                          )}
                          {apiKey.revoked_at ? "Revoked" : "Active"}
                        </Badge>
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
                            {!apiKey.revoked_at ? (
                              <DropdownMenuItem
                                disabled={revoke.isPending}
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
                <h3 className="font-medium">
                  {statusFilter === "revoked"
                    ? "No revoked API keys"
                    : "No active API keys"}
                </h3>
                <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">
                  {statusFilter === "revoked"
                    ? "Revoked keys will appear here."
                    : "Create a key for this workspace when you are ready to send your first inference request."}
                </p>
              </div>
            )}
          </section>
        </div>
      </main>

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
            className="rounded-lg border bg-muted p-3 font-mono text-xs leading-5 break-all"
            data-testid="api-key-secret"
          >
            {created?.secret}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={copySecret}>
              {copied ? (
                <Check className="size-4" />
              ) : (
                <Copy className="size-4" />
              )}
              {copied ? "Copied" : "Copy key"}
            </Button>
            <Button onClick={() => setCreated(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
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
  const mutation = useMutation({
    mutationFn: (values: CreateKeyValues) =>
      createApiKey(organizationId, workspaceId, {
        name: values.name,
        expires_at: values.expiresAt
          ? new Date(
              Date.UTC(
                values.expiresAt.getFullYear(),
                values.expiresAt.getMonth(),
                values.expiresAt.getDate(),
                23,
                59,
                59,
                999,
              ),
            ).toISOString()
          : null,
      }),
    onSuccess: (result) => {
      form.reset();
      onCreated(result);
    },
  });

  const submit = async (values: CreateKeyValues) => {
    try {
      await mutation.mutateAsync(values);
    } catch (error) {
      form.setError("root", {
        message:
          error instanceof Error
            ? error.message
            : "The API key could not be created.",
      });
    }
  };

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
                const tomorrow = new Date();
                tomorrow.setHours(0, 0, 0, 0);
                tomorrow.setDate(tomorrow.getDate() + 1);

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
                        disabled={{ before: tomorrow }}
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
            <Button type="submit" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? (
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
