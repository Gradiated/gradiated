import { useQuery } from "@tanstack/react-query";
import { Boxes, CircleCheck, LoaderCircle } from "lucide-react";

import {
  modelsQuery,
  type Model,
  type ServiceTierPricingPolicy,
} from "@/api/queries";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConsolePage, LoadFailed } from "@/pages/console-page";
import { formatUsd } from "@/lib/format";
import { tierPriceRows } from "@/pages/model-pricing";

const tierLabel = (policy: ServiceTierPricingPolicy): string => {
  const name =
    policy.service_tier.charAt(0).toUpperCase() + policy.service_tier.slice(1);
  if (policy.price_change_percent === 0) return name;

  const sign = policy.price_change_percent > 0 ? "+" : "";

  return `${name} (${sign}${policy.price_change_percent}%)`;
};

export const ModelsPage = () => {
  const models = useQuery(modelsQuery());

  return (
    <ConsolePage
      page="models"
      title="Models"
      description="Choose a model and copy its ID to start making requests."
    >
      {models.isLoading ? (
        <div className="grid min-h-64 place-items-center rounded-xl border bg-card">
          <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
        </div>
      ) : models.isError ? (
        <LoadFailed
          subject="models"
          retrying={models.isFetching}
          onRetry={() => void models.refetch()}
          className="min-h-64 rounded-xl border bg-card"
        />
      ) : models.data?.data.length ? (
        <div className="grid gap-5">
          {models.data.data.map((model) => (
            <article
              key={model.id}
              className="overflow-hidden rounded-xl border bg-card shadow-sm"
            >
              <div className="flex flex-col justify-between gap-5 border-b p-6 sm:flex-row sm:items-start">
                <div className="flex gap-4">
                  <span className="grid size-11 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground">
                    <Boxes className="size-5" />
                  </span>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-lg font-semibold">{model.name}</h2>
                      <span
                        className={
                          model.status === "available"
                            ? "inline-flex items-center gap-1 rounded-full bg-[#e9f6b9] px-2.5 py-1 text-xs text-[#3f4c12]"
                            : "rounded-full bg-muted px-2.5 py-1 text-xs text-muted-foreground"
                        }
                      >
                        {model.status === "available" ? (
                          <CircleCheck className="size-3" />
                        ) : null}
                        {model.status === "available"
                          ? "Available"
                          : "Unavailable"}
                      </span>
                    </div>
                    <code className="mt-1 block text-xs text-muted-foreground">
                      {model.id}
                    </code>
                  </div>
                </div>
              </div>
              <div className="grid gap-6 p-6 md:grid-cols-[1fr_auto]">
                <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
                  {model.properties.description}
                </p>
                <dl className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                  <Metric
                    label="Context"
                    value={formatTokens(
                      model.properties.input_modalities[0]?.supported_inputs
                        .max_context_length.value,
                    )}
                  />
                  <Metric
                    label="Max output"
                    value={formatTokens(
                      model.properties.output_modalities[0]?.max_length.value,
                    )}
                  />
                </dl>
              </div>
              <div className="border-t px-4 py-5 sm:px-6">
                <p className="mb-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Price per 1M tokens
                </p>
                <TierPricingTable
                  model={model}
                  policies={models.data.service_tiers}
                />
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="grid min-h-64 place-items-center rounded-xl border bg-card text-sm text-muted-foreground">
          No models are currently available.
        </div>
      )}
    </ConsolePage>
  );
};

const TierPricingTable = ({
  model,
  policies,
}: {
  model: Model;
  policies: ServiceTierPricingPolicy[];
}) => {
  const rows = tierPriceRows(model, policies);

  return (
    <Table className="min-w-[34rem] table-fixed">
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Token type</TableHead>
          {policies.map((policy) => (
            <TableHead
              key={policy.service_tier}
              className={
                policy.service_tier === "default"
                  ? "bg-muted/40 text-right"
                  : "text-right"
              }
            >
              {tierLabel(policy)}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.type}>
            <TableCell className="font-medium">{row.label}</TableCell>
            {row.prices.map(({ tier, usd }) => (
              <TableCell
                key={tier}
                className={
                  tier === "default"
                    ? "bg-muted/40 text-right font-medium"
                    : "text-right"
                }
              >
                {formatUsd(usd)}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};

const Metric = ({ label, value }: { label: string; value: string }) => (
  <div>
    <dt className="text-xs text-muted-foreground">{label}</dt>
    <dd className="mt-0.5 font-medium">{value}</dd>
  </div>
);

const formatTokens = (value: number | undefined) =>
  value === undefined ? "—" : new Intl.NumberFormat().format(value);
