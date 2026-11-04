import NiceModal from "@ebay/nice-modal-react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { createStaffOrganization, listStaffOrganizations } from "@/api/queries";
import { CreateNameDialog } from "@/components/create-name-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import {
  useProductContext,
  useScopeCreation,
} from "@/hooks/use-product-context";
import { ConsolePage } from "@/pages/console-page";

export const AdminPage = () => {
  const { user } = useProductContext();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const nextQuery = search.trim();
    if (nextQuery === query) return;

    const timer = setTimeout(() => {
      setQuery(nextQuery);
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [search, query]);
  const results = useQuery({
    queryKey: ["staff-organizations", query, offset],
    queryFn: () => listStaffOrganizations(query, offset),
    enabled: !!user?.is_staff && user.email_verified,
  });
  const { organizationCreated } = useScopeCreation();

  if (!user) return null;
  if (!user.is_staff || !user.email_verified)
    return <Navigate to="/api-keys" />;

  const organizations = results.data?.data ?? [];
  const create = () =>
    void NiceModal.show(CreateNameDialog, {
      title: "Prepare a customer organization",
      label: "Organization name",
      placeholder: "Acme Inc",
      submitLabel: "Create organization",
      emptyMessage: "Enter an organization name.",
      submit: async (name) => {
        await organizationCreated(await createStaffOrganization({ name }));
        await results.refetch();
      },
    });

  return (
    <ConsolePage
      page="admin"
      title="Admin portal"
      actions={
        <Button onClick={create}>
          <Plus />
          Create organization
        </Button>
      }
    >
      <section className="rounded-lg border bg-card">
        <div className="border-b px-5 py-4">
          <h2 className="font-medium">All organizations</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Workspace settings and invitations are saved before anyone signs up.
          </p>
        </div>
        <div className="border-b px-5 py-4">
          <Input
            type="search"
            aria-label="Search organizations"
            placeholder="Search organizations…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        {results.isError ? (
          <div className="p-4">
            Could not load organizations.{" "}
            <Button variant="link" onClick={() => void results.refetch()}>
              Retry
            </Button>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-5">Organization</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.isPending ? (
                <TableRow>
                  <TableCell colSpan={2} role="status">
                    Loading organizations…
                  </TableCell>
                </TableRow>
              ) : organizations.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={2} className="p-4">
                    {query
                      ? "No organizations match your search."
                      : "No organizations found."}
                  </TableCell>
                </TableRow>
              ) : (
                organizations.map((organization) => (
                  <TableRow key={organization.id}>
                    <TableCell className="py-2 pl-5">
                      <Link
                        to="/admin/organizations/$organizationId"
                        params={{ organizationId: organization.id }}
                        className="font-medium hover:underline"
                      >
                        {organization.name}
                      </Link>
                    </TableCell>
                    <TableCell className="py-2 capitalize">
                      {organization.status}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
        <div className="flex items-center justify-between border-t px-5 py-3 text-sm">
          <span>Page {Math.floor(offset / 20) + 1}</span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={offset === 0 || results.isFetching}
              onClick={() => setOffset(Math.max(0, offset - 20))}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!results.data?.has_more || results.isFetching}
              onClick={() => setOffset(offset + 20)}
            >
              Next
            </Button>
          </div>
        </div>
      </section>
    </ConsolePage>
  );
};
