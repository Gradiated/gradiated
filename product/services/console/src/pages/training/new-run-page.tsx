import { newIdempotencyKey } from "@gradiated/grad";
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { Calculator, LoaderCircle, Play } from "lucide-react";
import { useId, useMemo, useState, type ReactNode } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";

import { OptionSelect } from "@/components/option-select";
import { PlanSummary } from "@/components/training/plan-summary";
import { BackLink, SectionCard } from "@/components/training/training-ui";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  useBaseModels,
  useCreateRun,
  useDatasets,
  usePlanRun,
} from "@/hooks/use-grad";
import { useProductContext } from "@/hooks/use-product-context";
import { errorMessage } from "@/lib/errors";
import { formatCount } from "@/lib/grad/format";
import {
  DEFAULT_MODEL,
  RECIPE_OPTIONS,
  defaultModelFor,
  defaultRunForm,
  modelsForRecipe,
  runFormSchema,
  runRequest,
  usesTeacher,
  type RunForm,
} from "@/lib/grad/run-form";
import type { PlanRunRequest, PlanRunResponse } from "@/lib/grad/types";
import { cn } from "@/lib/utils";
import { ConsolePage } from "@/pages/console-page";

export const NewRunPage = () => {
  const { workspaceId } = useProductContext();
  const { dataset } = useSearch({ from: "/_training/training/runs/new" });

  return <NewRunForm key={workspaceId} initialDataset={dataset ?? ""} />;
};

const StepHeading = ({
  number,
  children,
}: {
  number: number;
  children: ReactNode;
}) => (
  <span className="flex items-center gap-2.5">
    <span className="grid size-6 place-items-center rounded-full bg-foreground text-xs font-semibold text-background">
      {number}
    </span>
    {children}
  </span>
);

interface Planned {
  request: PlanRunRequest;
  plan: PlanRunResponse;
  idempotencyKey: string;
}

const NewRunForm = ({ initialDataset }: { initialDataset: string }) => {
  const navigate = useNavigate();
  const ids = {
    name: useId(),
    cost: useId(),
    teacher: useId(),
    context: useId(),
    candidates: useId(),
    rubric: useId(),
  };
  const datasets = useDatasets();
  const models = useBaseModels();
  const planRun = usePlanRun();
  const createRun = useCreateRun();
  const [planned, setPlanned] = useState<Planned | null>(null);
  const form = useForm<RunForm>({
    resolver: zodResolver(runFormSchema),
    defaultValues: { ...defaultRunForm(initialDataset), model: DEFAULT_MODEL },
  });
  const values = useWatch({ control: form.control });
  const kind = values.kind ?? "sft";
  const datasetRows = datasets.data?.pages.flatMap((page) => page.data) ?? [];
  const recipeModels = modelsForRecipe(models.data ?? [], kind);
  const recipeDefault = defaultModelFor(models.data ?? [], kind);
  const current = useMemo(() => {
    const parsed = runFormSchema.safeParse(values);

    return parsed.success ? JSON.stringify(runRequest(parsed.data)) : null;
  }, [values]);
  const stale = planned !== null && JSON.stringify(planned.request) !== current;

  const estimate = form.handleSubmit((data) => {
    const request = runRequest(data);
    setPlanned(null);
    planRun.mutate(request, {
      onSuccess: (plan) =>
        setPlanned({ request, plan, idempotencyKey: newIdempotencyKey() }),
    });
  });

  const start = () => {
    if (!planned || stale) return;

    createRun.mutate(
      { request: planned.request, idempotencyKey: planned.idempotencyKey },
      {
        onSuccess: (run) =>
          void navigate({
            to: "/training/runs/$runId",
            params: { runId: run.id },
          }),
      },
    );
  };

  const errors = form.formState.errors;

  return (
    <ConsolePage
      page="training"
      title="New training run"
      description="Choose a dataset and a recipe, check the estimate, then start the run. Nothing is billed until it starts."
      back={<BackLink to="/training/runs">Training runs</BackLink>}
    >
      <form className="space-y-5" onSubmit={estimate} noValidate>
        <SectionCard title={<StepHeading number={1}>Dataset</StepHeading>}>
          {datasets.isPending ? (
            <Skeleton className="h-9 w-full" />
          ) : datasetRows.length ? (
            <Field data-invalid={Boolean(errors.dataset)}>
              <Controller
                control={form.control}
                name="dataset"
                render={({ field }) => (
                  <OptionSelect
                    label="Dataset"
                    placeholder="Choose a dataset"
                    value={field.value}
                    options={datasetRows.map((dataset) => ({
                      value: dataset.name,
                      label: `${dataset.name} · v${dataset.version} · ${formatCount(dataset.recordCount)} records`,
                    }))}
                    onValueChange={(name) => {
                      field.onChange(name);
                      if (!form.getFieldState("name").isDirty)
                        form.setValue(
                          "name",
                          `${name}-${form.getValues("kind")}`,
                        );
                    }}
                    className="w-full bg-card"
                  />
                )}
              />
              {errors.dataset ? <FieldError errors={[errors.dataset]} /> : null}
              <FieldDescription>
                The run trains on the dataset's current version.
              </FieldDescription>
            </Field>
          ) : (
            <p className="text-sm text-muted-foreground">
              No datasets yet.{" "}
              <Link
                to="/training/datasets"
                className="font-medium text-foreground underline underline-offset-4"
              >
                Import one
              </Link>{" "}
              to start training.
            </p>
          )}
        </SectionCard>

        <SectionCard title={<StepHeading number={2}>Recipe</StepHeading>}>
          <div className="space-y-6">
            <fieldset>
              <legend className="sr-only">Recipe</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {RECIPE_OPTIONS.map((option) => (
                  <label
                    key={option.value}
                    className={cn(
                      "flex cursor-pointer gap-3 rounded-lg border bg-card p-3 text-sm transition-colors hover:bg-muted/40",
                      kind === option.value &&
                        "border-foreground ring-1 ring-foreground",
                    )}
                  >
                    <input
                      type="radio"
                      value={option.value}
                      className="mt-1 accent-foreground"
                      {...form.register("kind", {
                        onChange: () => {
                          form.setValue("model", DEFAULT_MODEL);
                          if (
                            !form.getFieldState("name").isDirty &&
                            form.getValues("dataset")
                          )
                            form.setValue(
                              "name",
                              `${form.getValues("dataset")}-${option.value}`,
                            );
                        },
                      })}
                    />
                    <span>
                      <span className="font-medium">{option.label}</span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {option.description}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="grid gap-5 sm:grid-cols-2">
              <Field>
                <FieldLabel>Base model</FieldLabel>
                <Controller
                  control={form.control}
                  name="model"
                  render={({ field }) => (
                    <OptionSelect
                      label="Base model"
                      value={field.value}
                      disabled={models.isPending}
                      options={[
                        {
                          value: DEFAULT_MODEL,
                          label: recipeDefault
                            ? `Recipe default (${recipeDefault})`
                            : "Recipe default",
                        },
                        ...recipeModels.map((model) => ({
                          value: model.id,
                          label: model.id,
                        })),
                      ]}
                      onValueChange={field.onChange}
                      className="w-full bg-card"
                    />
                  )}
                />
              </Field>
              <Field data-invalid={Boolean(errors.name)}>
                <FieldLabel htmlFor={ids.name}>Run name</FieldLabel>
                <Input
                  id={ids.name}
                  autoComplete="off"
                  data-1p-ignore="true"
                  maxLength={64}
                  placeholder="support-sft"
                  {...form.register("name")}
                />
                {errors.name ? <FieldError errors={[errors.name]} /> : null}
              </Field>
              <Field data-invalid={Boolean(errors.maxCostUsd)}>
                <FieldLabel htmlFor={ids.cost}>
                  Cost cap (USD, optional)
                </FieldLabel>
                <Input
                  id={ids.cost}
                  inputMode="decimal"
                  autoComplete="off"
                  placeholder="No cap"
                  {...form.register("maxCostUsd")}
                />
                {errors.maxCostUsd ? (
                  <FieldError errors={[errors.maxCostUsd]} />
                ) : (
                  <FieldDescription>
                    The run stops with a checkpoint at the cap; you can resume
                    it.
                  </FieldDescription>
                )}
              </Field>
              {usesTeacher(kind) ? (
                <Field>
                  <FieldLabel htmlFor={ids.teacher}>Teacher model</FieldLabel>
                  <Input
                    id={ids.teacher}
                    autoComplete="off"
                    placeholder="qwen3-32b"
                    {...form.register("teacher")}
                  />
                </Field>
              ) : null}
              {kind === "router" ? (
                <>
                  <Field>
                    <FieldLabel htmlFor={ids.candidates}>
                      Candidate models (optional)
                    </FieldLabel>
                    <Input
                      id={ids.candidates}
                      autoComplete="off"
                      placeholder="Found in your records when empty"
                      {...form.register("candidates")}
                    />
                    <FieldDescription>
                      Separate model IDs with commas.
                    </FieldDescription>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor={ids.rubric}>
                      Score name (optional)
                    </FieldLabel>
                    <Input
                      id={ids.rubric}
                      autoComplete="off"
                      placeholder="resolved"
                      {...form.register("rubric")}
                    />
                  </Field>
                </>
              ) : null}
            </div>
            {kind === "cartridge" ? (
              <Field>
                <FieldLabel htmlFor={ids.context}>
                  Context to compress
                </FieldLabel>
                <Textarea
                  id={ids.context}
                  rows={5}
                  placeholder="Paste the document the cartridge should carry."
                  {...form.register("contextText")}
                />
              </Field>
            ) : null}
          </div>
        </SectionCard>

        <SectionCard
          title={<StepHeading number={3}>Estimate and start</StepHeading>}
          description="grad checks the dataset against the recipe and prices the run before anything is billed."
          actions={
            <Button
              type="submit"
              variant="outline"
              disabled={planRun.isPending}
            >
              {planRun.isPending ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <Calculator />
              )}
              {planned ? "Estimate again" : "Estimate cost"}
            </Button>
          }
        >
          {planRun.error ? (
            <p role="alert" className="text-sm text-destructive">
              {errorMessage(planRun.error, "Could not plan the run.")}
            </p>
          ) : planned ? (
            <div className={cn(stale && "opacity-50")}>
              <PlanSummary plan={planned.plan} />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No estimate yet.</p>
          )}

          {stale ? (
            <p className="mt-4 text-sm text-muted-foreground">
              The settings changed since this estimate. Estimate again to start.
            </p>
          ) : null}
          {createRun.error ? (
            <p role="alert" className="mt-4 text-sm text-destructive">
              {errorMessage(createRun.error, "Could not start the run.")}
            </p>
          ) : null}

          <div className="mt-5 flex justify-end border-t pt-5">
            <Button
              type="button"
              disabled={!planned || stale || createRun.isPending}
              onClick={start}
            >
              {createRun.isPending ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <Play />
              )}
              Start run
            </Button>
          </div>
        </SectionCard>
      </form>
    </ConsolePage>
  );
};
