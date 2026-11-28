import { Link, useNavigate } from "@tanstack/react-router";
import { Database, Upload } from "lucide-react";
import { useState } from "react";

import { ImportFileDialog } from "@/components/training/import-file-dialog";
import { StatusBadge } from "@/components/training/status-badge";
import {
  EmptyState,
  LoadMore,
  SkeletonRows,
  TableCard,
} from "@/components/training/training-ui";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDatasets, useSources } from "@/hooks/use-grad";
import { useProductContext } from "@/hooks/use-product-context";
import { formatCount, formatDateTime } from "@/lib/grad/format";
import { ConsolePage, LoadFailed } from "@/pages/console-page";

export const DatasetsPage = () => {
  const { workspaceId } = useProductContext();

  return <DatasetsPageBody key={workspaceId} />;
};

const DatasetsPageBody = () => {
  const navigate = useNavigate();
  const datasets = useDatasets();
  const sources = useSources();
  const [importOpen, setImportOpen] = useState(false);
  const rows = datasets.data?.pages.flatMap((page) => page.data) ?? [];

  const importButton = (
    <Button onClick={() => setImportOpen(true)}>
      <Upload />
      Import file
    </Button>
  );

  return (
    <ConsolePage
      page="training"
      title="Datasets"
      description="Versioned training data. Every import or source sync adds a version; runs pin the version they train on."
      width="wide"
      actions={importButton}
    >
      {datasets.isError ? (
        <LoadFailed
          subject="datasets"
          retrying={datasets.isFetching}
          onRetry={() => void datasets.refetch()}
          className="rounded-xl border bg-card"
        />
      ) : !datasets.isPending && !rows.length ? (
        <EmptyState
          icon={<Database />}
          title="No datasets yet"
          description="Import a JSONL, JSON or Parquet file of chat transcripts or traces, or connect a source with the grad SDK or CLI."
          action={importButton}
        />
      ) : (
        <TableCard
          label="Datasets"
          busy={datasets.isPending}
          footer={
            <LoadMore
              hasMore={datasets.hasNextPage}
              loading={datasets.isFetchingNextPage}
              onLoad={() => void datasets.fetchNextPage()}
            />
          }
        >
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-11 pl-5">Dataset</TableHead>
                <TableHead className="h-11">Version</TableHead>
                <TableHead className="h-11 text-right">Records</TableHead>
                <TableHead className="h-11">Sources</TableHead>
                <TableHead className="h-11 pr-5">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {datasets.isPending ? <SkeletonRows columns={5} /> : null}
              {rows.map((dataset) => {
                const own = (sources.data ?? []).filter(
                  (source) => source.dataset === dataset.name,
                );
                const paused = own.filter(
                  (source) => source.status === "paused",
                ).length;

                return (
                  <TableRow
                    key={dataset.id}
                    className="cursor-pointer"
                    onClick={() =>
                      void navigate({
                        to: "/training/datasets/$datasetName",
                        params: { datasetName: dataset.name },
                      })
                    }
                  >
                    <TableCell className="h-14 pl-5">
                      <Link
                        to="/training/datasets/$datasetName"
                        params={{ datasetName: dataset.name }}
                        onClick={(event) => event.stopPropagation()}
                        className="font-medium"
                      >
                        {dataset.name}
                      </Link>
                    </TableCell>
                    <TableCell className="tabular-nums">
                      v{dataset.version}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCount(dataset.recordCount)}
                    </TableCell>
                    <TableCell>
                      {own.length ? (
                        paused ? (
                          <StatusBadge
                            label={`${paused} paused`}
                            tone="warning"
                          />
                        ) : (
                          <span className="text-muted-foreground">
                            {own
                              .map((source) => source.provider.kind)
                              .join(", ")}
                          </span>
                        )
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="pr-5 text-muted-foreground">
                      {formatDateTime(dataset.updatedAt)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableCard>
      )}

      {importOpen ? (
        <ImportFileDialog open={importOpen} onOpenChange={setImportOpen} />
      ) : null}
    </ConsolePage>
  );
};
