import {
  Link,
  useNavigate,
  useParams,
  useSearch,
} from "@tanstack/react-router";
import { FlaskConical, Upload } from "lucide-react";
import { useState } from "react";

import { OptionTabs } from "@/components/option-select";
import { ImportFileDialog } from "@/components/training/import-file-dialog";
import { RecordsPreview } from "@/components/training/records-preview";
import {
  ImportsTable,
  SourcesTable,
} from "@/components/training/sources-table";
import { BackLink, TableCard } from "@/components/training/training-ui";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TabsContent } from "@/components/ui/tabs";
import { useDataset, useImports, useSources } from "@/hooks/use-grad";
import { useProductContext } from "@/hooks/use-product-context";
import { formatCount, formatDateTime } from "@/lib/grad/format";
import type { Dataset, ImportJob } from "@/lib/grad/types";
import { canManageOrganization } from "@/lib/roles";
import { ConsolePage, LoadFailed } from "@/pages/console-page";

export const DATASET_TABS = [
  { value: "records", label: "Records" },
  { value: "versions", label: "Versions" },
  { value: "sources", label: "Sources" },
  { value: "imports", label: "Imports" },
] as const;

export type DatasetTab = (typeof DATASET_TABS)[number]["value"];

const back = <BackLink to="/training/datasets">Datasets</BackLink>;

export const DatasetPage = () => {
  const { workspaceId } = useProductContext();
  const { datasetName } = useParams({
    from: "/training/datasets/$datasetName",
  });

  return (
    <DatasetPageBody key={`${workspaceId}:${datasetName}`} name={datasetName} />
  );
};

const DatasetPageBody = ({ name }: { name: string }) => {
  const dataset = useDataset(name);

  if (dataset.isPending) {
    return (
      <ConsolePage page="training" title={name} width="wide" back={back}>
        <div role="status" aria-label="Loading dataset" className="space-y-4">
          <Skeleton className="h-9 w-80" />
          <Skeleton className="h-72 w-full rounded-xl" />
        </div>
      </ConsolePage>
    );
  }

  if (dataset.isError) {
    return (
      <ConsolePage page="training" title={name} width="wide" back={back}>
        <LoadFailed
          subject="this dataset"
          retrying={dataset.isFetching}
          onRetry={() => void dataset.refetch()}
          className="rounded-xl border bg-card"
        />
      </ConsolePage>
    );
  }

  return <DatasetDetail dataset={dataset.data} />;
};

const DatasetDetail = ({ dataset }: { dataset: Dataset }) => {
  const navigate = useNavigate();
  const search = useSearch({ from: "/training/datasets/$datasetName" });
  const { selectedOrganization } = useProductContext();
  const sources = useSources();
  const imports = useImports();
  const [importOpen, setImportOpen] = useState(false);
  const tab = search.tab ?? "records";
  const version = search.version ?? dataset.version;
  const ownSources = (sources.data ?? []).filter(
    (source) => source.dataset === dataset.name,
  );
  const ownImports = (imports.data ?? []).filter(
    (job) => job.dataset === dataset.name,
  );

  const show = (next: { tab?: DatasetTab; version?: number }) =>
    void navigate({
      to: "/training/datasets/$datasetName",
      params: { datasetName: dataset.name },
      search: { ...search, ...next },
      replace: true,
    });

  return (
    <ConsolePage
      page="training"
      title={dataset.name}
      width="wide"
      back={back}
      description={`Version ${dataset.version} · ${formatCount(dataset.recordCount)} records · updated ${formatDateTime(dataset.updatedAt)}`}
      actions={
        <>
          <Button variant="outline" onClick={() => setImportOpen(true)}>
            <Upload />
            Import file
          </Button>
          {dataset.version === 0 ? (
            <Button disabled>
              <FlaskConical />
              Train on this dataset
            </Button>
          ) : (
            <Button asChild>
              <Link to="/training/runs/new" search={{ dataset: dataset.name }}>
                <FlaskConical />
                Train on this dataset
              </Link>
            </Button>
          )}
        </>
      }
    >
      <OptionTabs
        value={tab}
        options={DATASET_TABS}
        onValueChange={(next) => show({ tab: next })}
      >
        <TabsContent value="records">
          {dataset.version === 0 ? (
            <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
              No records yet. Import a file or sync a source to create the first
              version.
            </p>
          ) : (
            <RecordsPreview
              dataset={dataset.name}
              versions={dataset.version}
              version={version}
              onVersionChange={(next) => show({ version: next })}
            />
          )}
        </TabsContent>

        <TabsContent value="versions">
          <VersionsTable
            dataset={dataset}
            imports={ownImports}
            onView={(next) => show({ tab: "records", version: next })}
          />
        </TabsContent>

        <TabsContent value="sources">
          {sources.isPending ? (
            <Skeleton className="h-40 w-full rounded-xl" />
          ) : ownSources.length ? (
            <SourcesTable
              sources={ownSources}
              canSync={canManageOrganization(selectedOrganization)}
            />
          ) : (
            <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
              No sources feed this dataset. Connect Langfuse, LangSmith,
              Braintrust, PostHog, Phoenix or Gradiated traces with{" "}
              <code className="font-mono text-xs">grad sources add</code>.
            </p>
          )}
        </TabsContent>

        <TabsContent value="imports">
          {imports.isPending ? (
            <Skeleton className="h-40 w-full rounded-xl" />
          ) : ownImports.length ? (
            <ImportsTable imports={ownImports} />
          ) : (
            <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
              No recent imports.
            </p>
          )}
        </TabsContent>
      </OptionTabs>

      {importOpen ? (
        <ImportFileDialog
          dataset={dataset.name}
          open={importOpen}
          onOpenChange={setImportOpen}
        />
      ) : null}
    </ConsolePage>
  );
};

const VersionsTable = ({
  dataset,
  imports,
  onView,
}: {
  dataset: Dataset;
  imports: readonly ImportJob[];
  onView: (version: number) => void;
}) => {
  const byVersion = new Map(
    imports.flatMap((job) =>
      job.datasetVersion ? [[job.datasetVersion, job] as const] : [],
    ),
  );
  const versions = Array.from(
    { length: dataset.version },
    (_, index) => dataset.version - index,
  );

  return versions.length ? (
    <TableCard label="Versions">
      <Table>
        <TableHeader className="bg-muted/40">
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-11 pl-5">Version</TableHead>
            <TableHead className="h-11">Added by</TableHead>
            <TableHead className="h-11 text-right">Records added</TableHead>
            <TableHead className="h-11">Created</TableHead>
            <TableHead className="h-11 pr-5 text-right" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {versions.map((version) => {
            const job = byVersion.get(version);

            return (
              <TableRow key={version}>
                <TableCell className="h-12 pl-5 font-medium tabular-nums">
                  v{version}
                  {version === dataset.version ? (
                    <span className="ml-2 text-xs font-normal text-muted-foreground">
                      current
                    </span>
                  ) : null}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {job
                    ? job.source.kind === "upload"
                      ? "File upload"
                      : "Import or sync"
                    : "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {job ? formatCount(job.importedCount) : "—"}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {job ? formatDateTime(job.updatedAt) : "—"}
                </TableCell>
                <TableCell className="pr-5 text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onView(version)}
                  >
                    View records
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableCard>
  ) : (
    <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
      No versions yet.
    </p>
  );
};
