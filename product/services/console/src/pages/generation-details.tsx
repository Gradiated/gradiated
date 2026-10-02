import { ModelLabel } from "@/components/model-label";
import { Check } from "lucide-react";
import type { ReactNode } from "react";

import type { GenerationLog } from "@/api/queries";
import { CopyStateIcon } from "@/components/copy-state-icon";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { copyLabel, useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { formatLatency, formatNanoUsd } from "@/lib/format";

const completedAt = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "medium",
});

const preciseTimestamp = new Intl.DateTimeFormat(undefined, {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  fractionalSecondDigits: 3,
});

const timestamp = (value: string) => preciseTimestamp.format(new Date(value));

const elapsedMs = (from: string, to: string) =>
  new Date(to).getTime() - new Date(from).getTime();

export const generationLatency = (generation: GenerationLog) =>
  elapsedMs(generation.received_at, generation.completed_at);

const STATUS_BADGE_CLASS: Record<GenerationLog["status"], string> = {
  succeeded: "border-[#cadb87] bg-[#f2f7d9] text-[#475617]",
  failed: "border-destructive/25 bg-destructive/5 text-destructive",
  cancelled: "border-border bg-muted text-muted-foreground",
  abandoned: "border-[#e4c880] bg-[#fbf3db] text-[#755b15]",
};

export const StatusBadge = ({
  status,
}: {
  status: GenerationLog["status"];
}) => (
  <Badge variant="outline" className={STATUS_BADGE_CLASS[status]}>
    {status === "succeeded" ? <Check /> : null}
    {status[0]?.toUpperCase()}
    {status.slice(1)}
  </Badge>
);

export const GenerationDetails = ({
  generation,
}: {
  generation: GenerationLog;
}) => {
  const idCopy = useCopyToClipboard();
  const firstToken = generation.first_token_at
    ? elapsedMs(generation.received_at, generation.first_token_at)
    : null;

  return (
    <SheetContent className="w-full overflow-y-auto p-0 sm:max-w-xl">
      <SheetHeader className="border-b p-6 pr-12">
        <div className="flex items-center gap-2">
          <StatusBadge status={generation.status} />
          <span className="text-xs text-muted-foreground">
            {completedAt.format(new Date(generation.completed_at))}
          </span>
        </div>
        <SheetTitle className="mt-3 flex items-center gap-2 font-mono text-sm font-medium">
          {generation.id}
          <button
            type="button"
            onClick={() => void idCopy.copy(generation.id)}
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label={copyLabel(idCopy.state, "Copy generation ID")}
          >
            <CopyStateIcon state={idCopy.state} className="size-3.5" />
          </button>
        </SheetTitle>
        <SheetDescription>Request details and measured usage.</SheetDescription>
      </SheetHeader>

      <div className="space-y-7 p-6">
        <DetailSection title="Overview">
          <DetailGrid>
            <Detail
              label="Model"
              value={<ModelLabel id={generation.model_id} />}
            />
            <Detail label="Cost" value={formatNanoUsd(generation.charge)} />
            <Detail
              label="Latency"
              value={formatLatency(generationLatency(generation))}
            />
            <Detail
              label="Streamed"
              value={generation.streamed ? "Yes" : "No"}
            />
          </DetailGrid>
        </DetailSection>

        <Separator />
        <DetailSection title="Token usage">
          <DetailGrid>
            <Detail
              label="Input"
              value={generation.input_tokens.toLocaleString()}
            />
            <Detail
              label="Output"
              value={generation.output_tokens.toLocaleString()}
            />
            <Detail
              label="Cached input"
              value={generation.cached_input_tokens.toLocaleString()}
            />
            <Detail
              label="Reasoning"
              value={generation.reasoning_tokens.toLocaleString()}
            />
          </DetailGrid>
        </DetailSection>

        <Separator />
        <DetailSection title="Outcome">
          <dl className="divide-y rounded-lg border">
            <Property
              label="Finish reason"
              value={generation.finish_reason ?? "—"}
            />
            <Property label="Error code" value={generation.error_code ?? "—"} />
            <Property
              label="Output delivered"
              value={generation.usable_output_delivered ? "Yes" : "No"}
            />
            <Property
              label="Cancellation owner"
              value={generation.cancellation_owner ?? "—"}
            />
            <Property
              label="External ID"
              value={generation.external_id ?? "—"}
            />
          </dl>
        </DetailSection>

        <Separator />
        <DetailSection title="Timing">
          <dl className="divide-y rounded-lg border">
            <Property
              label="Received"
              value={timestamp(generation.received_at)}
            />
            <Property
              label="Started"
              value={
                generation.started_at ? timestamp(generation.started_at) : "—"
              }
            />
            <Property
              label="Time to first token"
              value={
                firstToken === null ? "—" : `${firstToken.toLocaleString()} ms`
              }
            />
            <Property
              label="Completed"
              value={timestamp(generation.completed_at)}
            />
          </dl>
        </DetailSection>
      </div>
    </SheetContent>
  );
};

const DetailSection = ({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) => (
  <section>
    <h3 className="mb-3 text-sm font-medium">{title}</h3>
    {children}
  </section>
);

const DetailGrid = ({ children }: { children: ReactNode }) => (
  <dl className="grid grid-cols-2 gap-x-6 gap-y-5">{children}</dl>
);

const Detail = ({ label, value }: { label: string; value: ReactNode }) => (
  <div className="min-w-0">
    <dt className="text-xs text-muted-foreground">{label}</dt>
    <dd className="mt-1 truncate text-sm font-medium">{value}</dd>
  </div>
);

const Property = ({ label, value }: { label: string; value: string }) => (
  <div className="flex items-center justify-between gap-4 px-3 py-2.5 text-xs">
    <dt className="text-muted-foreground">{label}</dt>
    <dd className="max-w-[65%] truncate text-right font-medium">{value}</dd>
  </div>
);
