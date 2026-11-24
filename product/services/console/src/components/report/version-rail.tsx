import {
  catalogModel,
  type CatalogEntry,
} from "@gradiated/contracts/model-catalog";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight } from "lucide-react";
import type { ReactNode } from "react";

import { modelsQuery } from "@/api/queries";
import { ModelLabel } from "@/components/model-label";
import { formatFileSize, formatUsd } from "@/lib/format";
import { tierPriceRows } from "@/pages/model-pricing";

export const RailSection = ({
  title,
  aside,
  children,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
}) => (
  <section className="flex flex-col gap-2.5 border-t py-5">
    <div className="flex items-baseline justify-between gap-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h2>
      {aside}
    </div>
    {children}
  </section>
);

const Detail = ({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) => (
  <div className="flex items-baseline justify-between gap-4 text-sm">
    <dt className="shrink-0 text-muted-foreground">{label}</dt>
    <dd className="min-w-0 truncate text-right">{children}</dd>
  </div>
);

export const ReportContents = ({
  headings,
}: {
  headings: readonly { id: string; title: string }[] | undefined;
}) =>
  headings?.length ? (
    <RailSection title="On this page">
      <nav aria-label="On this page" className="flex flex-col">
        {headings.map((heading) => (
          <a
            key={heading.id}
            href={`#${heading.id}`}
            className="border-l-2 border-border px-3 py-1 text-sm text-muted-foreground hover:border-foreground hover:text-foreground"
          >
            {heading.title}
          </a>
        ))}
      </nav>
    </RailSection>
  ) : null;

export const VersionFacts = ({
  baseModelId,
  checkpoint,
  adapter,
  sizeBytes,
}: {
  baseModelId: string;
  checkpoint: string | null | undefined;
  adapter: string;
  sizeBytes: number;
}) => {
  const models = useQuery(modelsQuery());
  const baseModel = models.data?.data.find((model) => model.id === baseModelId);
  const defaultTier = (models.data?.service_tiers ?? []).filter(
    (policy) => policy.service_tier === "default",
  );
  const prices =
    baseModel?.properties && defaultTier.length
      ? tierPriceRows(baseModel, defaultTier)
      : [];
  const repository =
    (catalogModel(baseModelId) as CatalogEntry | undefined)?.training?.model ??
    baseModel?.properties?.hugging_face_id ??
    baseModelId;

  return (
    <>
      {prices.length ? (
        <RailSection
          title="Pricing"
          aside={
            <span className="text-xs text-muted-foreground">per 1M tokens</span>
          }
        >
          <dl className="flex flex-col gap-2">
            {prices.map((row) => (
              <Detail key={row.type} label={row.label}>
                <span className="tabular-nums">
                  {formatUsd(row.prices[0]?.usd ?? 0)}
                </span>
              </Detail>
            ))}
          </dl>
        </RailSection>
      ) : null}

      <RailSection title="Details">
        <dl className="flex flex-col gap-2">
          <Detail label="Base model">
            <ModelLabel id={baseModelId} />
          </Detail>
          <Detail label="Checkpoint">
            {checkpoint ? (
              <a
                href={`https://huggingface.co/${repository}/tree/${checkpoint}`}
                target="_blank"
                rel="noreferrer"
                title={checkpoint}
                className="inline-flex items-center gap-1 font-mono text-xs underline decoration-border underline-offset-4 hover:decoration-foreground"
              >
                {checkpoint.slice(0, 12)}
                <ArrowUpRight aria-hidden className="size-3" />
              </a>
            ) : (
              <span className="text-muted-foreground">Unknown</span>
            )}
          </Detail>
          <Detail label="Adapter">{adapter}</Detail>
          <Detail label="Size">{formatFileSize(sizeBytes)}</Detail>
        </dl>
      </RailSection>
    </>
  );
};
