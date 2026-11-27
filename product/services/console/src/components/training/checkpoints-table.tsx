import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { SectionCard, SkeletonRows } from "@/components/training/training-ui";
import { formatBytes, formatCount, formatDateTime } from "@/lib/grad/format";
import { formatMetric } from "@/lib/grad/eval-report";
import { FORMAT_LABEL } from "@/lib/grad/labels";
import type { Checkpoint } from "@/lib/grad/types";

export const CheckpointsTable = ({
  checkpoints,
  loading,
}: {
  checkpoints: readonly Checkpoint[];
  loading: boolean;
}) => (
  <SectionCard
    title="Checkpoints"
    description="Saved during training and at each eval step."
    contentClassName="p-0"
  >
    {!loading && !checkpoints.length ? (
      <p className="p-5 text-sm text-muted-foreground">No checkpoints yet.</p>
    ) : (
      <div className="overflow-x-auto">
        <Table>
          <TableHeader className="bg-muted/40">
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-5">Step</TableHead>
              <TableHead>Attempt</TableHead>
              <TableHead>Eval score</TableHead>
              <TableHead>Format</TableHead>
              <TableHead>Size</TableHead>
              <TableHead className="pr-5">Expires</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? <SkeletonRows columns={6} rows={3} /> : null}
            {[...checkpoints]
              .sort((a, b) => b.step - a.step)
              .map((checkpoint) => (
                <TableRow key={checkpoint.id}>
                  <TableCell className="pl-5 font-medium tabular-nums">
                    <span className="flex items-center gap-2">
                      {formatCount(checkpoint.step)}
                      {checkpoint.best ? (
                        <Badge variant="secondary">Best</Badge>
                      ) : null}
                      {checkpoint.final ? (
                        <Badge variant="outline">Final</Badge>
                      ) : null}
                    </span>
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {checkpoint.attempt}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {checkpoint.evalScore === null
                      ? "—"
                      : formatMetric(checkpoint.evalScore)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {checkpoint.format
                      ? (FORMAT_LABEL[checkpoint.format] ?? checkpoint.format)
                      : "Training state"}
                  </TableCell>
                  <TableCell className="tabular-nums text-muted-foreground">
                    {formatBytes(checkpoint.sizeBytes)}
                  </TableCell>
                  <TableCell className="pr-5 text-muted-foreground">
                    {checkpoint.expiresAt
                      ? formatDateTime(checkpoint.expiresAt)
                      : "Kept"}
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>
    )}
  </SectionCard>
);
