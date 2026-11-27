import { ChevronDown, ChevronRight } from "lucide-react";
import { Fragment, useState } from "react";

import { OptionSelect } from "@/components/option-select";
import {
  LoadMore,
  SkeletonRows,
  TableCard,
} from "@/components/training/training-ui";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDatasetRecords } from "@/hooks/use-grad";
import { formatCount } from "@/lib/grad/format";
import { recordPreview, recordScores } from "@/lib/grad/records";
import type { DatasetRecord } from "@/lib/grad/types";
import { LoadFailed } from "@/pages/console-page";

export const RecordsTable = ({
  records,
  loading,
}: {
  records: readonly DatasetRecord[];
  loading: boolean;
}) => {
  const [open, setOpen] = useState<number | null>(null);

  return (
    <Table>
      <TableHeader className="bg-muted/40">
        <TableRow className="hover:bg-transparent">
          <TableHead className="h-11 w-8 pl-5" />
          <TableHead className="h-11">Input</TableHead>
          <TableHead className="h-11">Output</TableHead>
          <TableHead className="h-11 pr-5">Scores</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {loading ? <SkeletonRows columns={4} /> : null}
        {records.map((record, index) => {
          const preview = recordPreview(record);
          const expanded = open === index;

          return (
            <Fragment key={record.id ?? index}>
              <TableRow
                className="cursor-pointer align-top"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : index)}
              >
                <TableCell className="pl-5 text-muted-foreground">
                  {expanded ? (
                    <ChevronDown className="size-4" />
                  ) : (
                    <ChevronRight className="size-4" />
                  )}
                </TableCell>
                <TableCell className="max-w-md py-3 whitespace-normal">
                  <p className="line-clamp-3 text-sm">{preview.input || "—"}</p>
                </TableCell>
                <TableCell className="max-w-md py-3 whitespace-normal">
                  <p className="line-clamp-3 text-sm text-muted-foreground">
                    {preview.output || "—"}
                  </p>
                </TableCell>
                <TableCell className="py-3 pr-5">
                  <span className="flex flex-wrap gap-1">
                    {recordScores(record).map((score) => (
                      <Badge
                        key={score}
                        variant="secondary"
                        className="font-mono font-normal"
                      >
                        {score}
                      </Badge>
                    ))}
                  </span>
                </TableCell>
              </TableRow>
              {expanded ? (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={4} className="bg-muted/30 px-5 py-4">
                    <pre className="max-h-96 overflow-auto font-mono text-xs leading-5 whitespace-pre-wrap">
                      {JSON.stringify(record, null, 2)}
                    </pre>
                  </TableCell>
                </TableRow>
              ) : null}
            </Fragment>
          );
        })}
      </TableBody>
    </Table>
  );
};

export const RecordsPreview = ({
  dataset,
  versions,
  version,
  onVersionChange,
}: {
  dataset: string;
  versions: number;
  version: number;
  onVersionChange: (version: number) => void;
}) => {
  const records = useDatasetRecords(dataset, version);
  const rows = records.data?.pages.flatMap((page) => page.data) ?? [];
  const total = records.data?.pages[0]?.total;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {total === undefined
            ? "Loading records…"
            : `${formatCount(total)} records in version ${version}`}
        </p>
        <OptionSelect
          label="Dataset version"
          value={String(version)}
          options={Array.from({ length: versions }, (_, index) => {
            const value = versions - index;

            return {
              value: String(value),
              label:
                value === versions
                  ? `Version ${value} (current)`
                  : `Version ${value}`,
            };
          })}
          onValueChange={(value) => onVersionChange(Number(value))}
          className="min-w-44 bg-card"
        />
      </div>
      {records.isError ? (
        <LoadFailed
          subject="records"
          retrying={records.isFetching}
          onRetry={() => void records.refetch()}
          className="rounded-xl border bg-card"
        />
      ) : (
        <TableCard
          label="Records"
          busy={records.isPending}
          footer={
            <LoadMore
              hasMore={records.hasNextPage}
              loading={records.isFetchingNextPage}
              onLoad={() => void records.fetchNextPage()}
            />
          }
        >
          <RecordsTable records={rows} loading={records.isPending} />
        </TableCard>
      )}
    </div>
  );
};
