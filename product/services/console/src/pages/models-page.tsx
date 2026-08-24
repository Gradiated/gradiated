import { useQuery } from "@tanstack/react-query";
import { Boxes, CircleCheck, LoaderCircle } from "lucide-react";

import { listModels, type Model } from "@/api/queries";
import { AppShell } from "@/components/app-shell";
import { useProductContext } from "@/hooks/use-product-context";
import { formatUsd } from "@/lib/format";

const pricePerMillion = (model: Model, unit: "prompt" | "completion") => {
  const modality =
    unit === "prompt"
      ? model.properties.input_modalities[0]
      : model.properties.output_modalities[0];
  if (!modality) return "—";
  const price = modality.pricing.find((entry) => entry.type === unit);
  if (!price) return "—";
  return formatUsd(price.cost / 1_000);
};

export const ModelsPage = () => {
  const context = useProductContext();
  const models = useQuery({ queryKey: ["models"], queryFn: listModels });

  return (
    <AppShell
      user={context.user}
      organizationId={context.organizationId}
      workspaces={context.workspaces}
      workspaceId={context.workspaceId}
      onSelectOrganization={context.selectOrganization}
      onSelectWorkspace={context.selectWorkspace}
      onSignOut={context.signOut}
      activePage="models"
      pageTitle="Models"
    >
      <main className="min-w-0 flex-1 px-5 py-8 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-5xl">
          <div className="mb-8">
            <h1 className="text-3xl font-semibold tracking-[-0.035em]">
              Models
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Choose a model and copy its ID to start making requests.
            </p>
          </div>

          {models.isLoading ? (
            <div className="grid min-h-64 place-items-center rounded-xl border bg-card">
              <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
            </div>
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
                          <h2 className="text-lg font-semibold">
                            {model.name}
                          </h2>
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
                    <div className="flex gap-6 text-sm">
                      <Price
                        label="Input"
                        value={pricePerMillion(model, "prompt")}
                      />
                      <Price
                        label="Output"
                        value={pricePerMillion(model, "completion")}
                      />
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
                          model.properties.output_modalities[0]?.max_length
                            .value,
                        )}
                      />
                    </dl>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="grid min-h-64 place-items-center rounded-xl border bg-card text-sm text-muted-foreground">
              No models are currently available.
            </div>
          )}
        </div>
      </main>
    </AppShell>
  );
};

const Price = ({ label, value }: { label: string; value: string }) => (
  <div>
    <p className="text-xs text-muted-foreground">{label}</p>
    <p className="mt-0.5 font-medium">{value} / 1M</p>
  </div>
);

const Metric = ({ label, value }: { label: string; value: string }) => (
  <div>
    <dt className="text-xs text-muted-foreground">{label}</dt>
    <dd className="mt-0.5 font-medium">{value}</dd>
  </div>
);

const formatTokens = (value: number | undefined) =>
  value === undefined ? "—" : new Intl.NumberFormat().format(value);
