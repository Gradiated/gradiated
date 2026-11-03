import NiceModal from "@ebay/nice-modal-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, Navigate, useParams } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";

import {
  getStaffOrganization,
  listMembers,
  startImpersonation,
} from "@/api/queries";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useProductContext } from "@/hooks/use-product-context";
import { errorMessage } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { ConsolePage, LoadFailed } from "@/pages/console-page";
import { InviteMembersDialog } from "@/pages/settings/invite-members-dialog";
import { switchConsoleIdentity } from "@/lib/session-sync";

export const AdminOrganizationPage = () => {
  const { organizationId } = useParams({
    from: "/admin/organizations/$organizationId",
  });
  const { user } = useProductContext();
  const isStaff = user?.is_staff === true && user.email_verified;
  const details = useQuery({
    queryKey: ["staff-organization", organizationId],
    queryFn: () => getStaffOrganization(organizationId),
    enabled: isStaff,
  });
  const organization = details.data;
  const members = useQuery({
    queryKey: queryKeys.members(organizationId),
    queryFn: () => listMembers(organizationId),
    enabled: isStaff && !!organization,
  });
  const impersonate = useMutation({
    mutationFn: startImpersonation,
    onSuccess: () => {
      switchConsoleIdentity("/api-keys");
    },
    onError: (error) =>
      toast.error(errorMessage(error, "Could not impersonate this user.")),
  });

  if (!user) return null;
  if (!isStaff) return <Navigate to="/api-keys" />;

  return (
    <ConsolePage
      page="admin"
      title={organization?.name ?? "Organization"}
      back={
        <Button variant="link" size="sm" asChild className="mb-5 px-0">
          <Link to="/admin">
            <ArrowLeft aria-hidden="true" />
            All organizations
          </Link>
        </Button>
      }
      actions={
        organization?.status === "active" ? (
          <>
            <Button
              onClick={() =>
                void NiceModal.show(InviteMembersDialog, {
                  organizationId,
                  organizationName: organization.name,
                })
              }
            >
              Invite people
            </Button>
          </>
        ) : null
      }
    >
      {details.isPending ? (
        <p role="status">Loading organization…</p>
      ) : details.isError ? (
        <LoadFailed
          subject="organization"
          retrying={details.isFetching}
          onRetry={() => void details.refetch()}
        />
      ) : organization ? (
        <section className="rounded-lg border bg-card">
          <div className="border-b p-5">
            <h2 className="font-medium">Users</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Impersonation opens the console with that user's permissions for
              up to 15 minutes.
            </p>
          </div>
          {members.isError ? (
            <LoadFailed
              subject="users"
              retrying={members.isFetching}
              onRetry={() => void members.refetch()}
            />
          ) : members.isPending ? (
            <p role="status" className="p-5 text-sm">
              Loading users…
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-5">Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead className="text-right" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.data?.data.map((member) => (
                  <TableRow key={member.user_id}>
                    <TableCell className="pl-5">{member.email}</TableCell>
                    <TableCell>
                      {member.role === "admin" ? "Admin" : "Member"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={
                          impersonate.isPending || member.user_id === user.id
                        }
                        aria-label={`Impersonate ${member.email}`}
                        onClick={() => impersonate.mutate(member.user_id)}
                      >
                        Impersonate
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {members.data?.data.length === 0 ? (
            <p className="p-5 text-sm text-muted-foreground">
              No users have joined yet. Invite people to give them access.
            </p>
          ) : null}
        </section>
      ) : null}
    </ConsolePage>
  );
};
