import NiceModal from "@ebay/nice-modal-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNowStrict } from "date-fns";
import { LoaderCircle, Mail, MoreHorizontal, Plus } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";

import {
  listInvitations,
  listMembers,
  removeMember,
  resendInvitation,
  revokeInvitation,
  updateMember,
  type OrganizationRole,
} from "@/api/queries";
import { OptionSelect } from "@/components/option-select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useIsMobile } from "@/hooks/use-mobile";
import { useProductContext } from "@/hooks/use-product-context";
import { errorMessage } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { ROLE_OPTIONS, canManageOrganization, roleLabel } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { LoadFailed } from "@/pages/console-page";
import { InviteMembersDialog } from "./invite-members-dialog";
import { SettingsHeader } from "./settings-layout";

const joinedDate = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export const MembersSettingsPage = () => {
  const { user, organizationId, selectedOrganization } = useProductContext();
  const client = useQueryClient();
  const canManage = canManageOrganization(selectedOrganization);
  const compact = useIsMobile();
  const organizationName = selectedOrganization?.name ?? "this organization";
  const members = useQuery({
    queryKey: queryKeys.members(organizationId),
    queryFn: () => listMembers(organizationId),
    enabled: organizationId !== "",
  });
  const invitations = useQuery({
    queryKey: queryKeys.invitations(organizationId),
    queryFn: () => listInvitations(organizationId),
    enabled: organizationId !== "",
  });

  const reload = (queryKey: readonly unknown[]) => () =>
    client.invalidateQueries({ queryKey });
  const report = (fallback: string) => (error: Error) =>
    toast.error(errorMessage(error, fallback));

  const changeRole = useMutation({
    mutationFn: (change: { userId: string; role: OrganizationRole }) =>
      updateMember(organizationId, change.userId, change.role),
    onSuccess: reload(queryKeys.members(organizationId)),
    onError: report("The role could not be changed."),
  });
  const remove = useMutation({
    mutationFn: (userId: string) => removeMember(organizationId, userId),
    onSuccess: reload(queryKeys.members(organizationId)),
    onError: report("The member could not be removed."),
  });
  const resend = useMutation({
    mutationFn: (invitationId: string) =>
      resendInvitation(organizationId, invitationId),
    onSuccess: (invitation) => {
      toast.success(`Invitation sent to ${invitation.email}.`);
      return reload(queryKeys.invitations(organizationId))();
    },
    onError: report("The invitation could not be sent."),
  });
  const revoke = useMutation({
    mutationFn: (invitationId: string) =>
      revokeInvitation(organizationId, invitationId),
    onSuccess: reload(queryKeys.invitations(organizationId)),
    onError: report("The invitation could not be revoked."),
  });
  const busy = [changeRole, remove, resend, revoke].some(
    (mutation) => mutation.isPending,
  );

  const invite = () =>
    void NiceModal.show(InviteMembersDialog, {
      organizationId,
      organizationName,
    });
  const failure = [members, invitations].find((query) => query.isError);

  return (
    <>
      <SettingsHeader
        title="Members"
        description="Admins can invite people, manage members and billing."
        actions={
          canManage ? (
            <Button onClick={invite}>
              <Plus />
              {compact ? "Invite" : "Invite members"}
            </Button>
          ) : null
        }
      />
      <section className="overflow-hidden rounded-lg border bg-card">
        {members.isLoading || invitations.isLoading ? (
          <div className="grid min-h-48 place-items-center">
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : failure ? (
          <LoadFailed
            subject="members"
            retrying={failure.isFetching}
            onRetry={() => void failure.refetch()}
          />
        ) : (
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-11 pl-5">Member</TableHead>
                {compact ? null : (
                  <>
                    <TableHead className="h-11 w-36 px-4">Role</TableHead>
                    <TableHead className="h-11 w-36 px-4">Joined</TableHead>
                  </>
                )}
                <TableHead className="h-11 w-14 pr-3 text-right">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.data?.data.map((member) => {
                const editable = canManage && member.user_id !== user?.id;

                return (
                  <PersonRow
                    key={member.user_id}
                    compact={compact}
                    avatar={
                      <Avatar className="bg-muted uppercase">
                        {member.email.charAt(0)}
                      </Avatar>
                    }
                    title={member.email}
                    badge={
                      member.user_id === user?.id ? (
                        <Badge variant="secondary" className="font-normal">
                          You
                        </Badge>
                      ) : null
                    }
                    role={
                      editable ? (
                        <OptionSelect
                          value={member.role}
                          options={ROLE_OPTIONS}
                          onValueChange={(role) =>
                            changeRole.mutate({ userId: member.user_id, role })
                          }
                          label={`Role for ${member.email}`}
                          className="h-8 w-28"
                          disabled={busy}
                        />
                      ) : (
                        <Badge variant="secondary">
                          {roleLabel(member.role)}
                        </Badge>
                      )
                    }
                    joined={joinedDate.format(new Date(member.joined_at))}
                    actionsLabel={`Actions for ${member.email}`}
                    actions={
                      editable ? (
                        <DropdownMenuItem
                          disabled={busy}
                          className="text-destructive focus:text-destructive"
                          onSelect={() => {
                            if (
                              window.confirm(
                                `Remove ${member.email} from ${organizationName}?`,
                              )
                            )
                              remove.mutate(member.user_id);
                          }}
                        >
                          Remove from {organizationName}
                        </DropdownMenuItem>
                      ) : null
                    }
                  />
                );
              })}
              {invitations.data?.data.map((invitation) => {
                const expiresAt = new Date(invitation.expires_at);
                const expired = expiresAt.getTime() <= Date.now();

                return (
                  <PersonRow
                    key={invitation.id}
                    compact={compact}
                    avatar={
                      <Avatar className="bg-[#fff3c4] text-[#5a4a10]">
                        <Mail className="size-3.5" />
                      </Avatar>
                    }
                    title={invitation.email}
                    subtitle={`Invited by ${invitation.invited_by_email} · ${
                      expired
                        ? "expired"
                        : `expires in ${formatDistanceToNowStrict(expiresAt)}`
                    }`}
                    role={
                      <Badge
                        className={
                          expired
                            ? "bg-muted text-muted-foreground"
                            : "bg-[#fff3c4] text-[#5a4a10]"
                        }
                      >
                        {expired ? "Expired" : "Invited"} ·{" "}
                        {roleLabel(invitation.role)}
                      </Badge>
                    }
                    joined="—"
                    actionsLabel={`Actions for the invitation to ${invitation.email}`}
                    actions={
                      canManage ? (
                        <>
                          <DropdownMenuItem
                            disabled={busy}
                            onSelect={() => resend.mutate(invitation.id)}
                          >
                            Resend invitation
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            disabled={busy}
                            className="text-destructive focus:text-destructive"
                            onSelect={() => {
                              if (
                                window.confirm(
                                  `Revoke the invitation to ${invitation.email}?`,
                                )
                              )
                                revoke.mutate(invitation.id);
                            }}
                          >
                            Revoke
                          </DropdownMenuItem>
                        </>
                      ) : null
                    }
                  />
                );
              })}
            </TableBody>
          </Table>
        )}
      </section>
    </>
  );
};

const Avatar = ({
  className,
  children,
}: {
  className: string;
  children: ReactNode;
}) => (
  <span
    className={cn(
      "grid size-8 shrink-0 place-items-center rounded-full text-xs font-medium",
      className,
    )}
  >
    {children}
  </span>
);

const PersonRow = ({
  compact,
  avatar,
  title,
  badge,
  subtitle,
  role,
  joined,
  actionsLabel,
  actions,
}: {
  compact: boolean;
  avatar: ReactNode;
  title: string;
  badge?: ReactNode;
  subtitle?: string;
  role: ReactNode;
  joined: string;
  actionsLabel: string;
  actions: ReactNode;
}) => (
  <TableRow>
    <TableCell className="h-16 max-w-0 py-3 pl-5">
      <div className="flex items-center gap-3">
        {avatar}
        <div className="min-w-0 space-y-1.5">
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <span className="truncate font-medium">{title}</span>
              {badge}
            </div>
            {subtitle ? (
              <p className="truncate text-xs text-muted-foreground">
                {subtitle}
              </p>
            ) : null}
          </div>
          {compact ? role : null}
        </div>
      </div>
    </TableCell>
    {compact ? null : (
      <>
        <TableCell className="px-4">{role}</TableCell>
        <TableCell className="px-4 text-muted-foreground">{joined}</TableCell>
      </>
    )}
    <TableCell className="pr-3 text-right">
      {actions ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label={actionsLabel}>
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            {actions}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </TableCell>
  </TableRow>
);
