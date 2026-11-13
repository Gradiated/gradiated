import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  WORKLOAD_BENCHMARK_FILE,
  WorkloadBenchmarkSchema,
  type WorkloadBenchmark,
} from "@gradiated/contracts";
import { modelsForUseCase } from "@gradiated/contracts/model-catalog";
import {
  completeVersionFile,
  createVersionFile,
  deleteVersionFile,
} from "@/api/training";
import { useWorkloadBenchmark } from "@/hooks/use-workload-benchmark";
import { useProductContext } from "@/hooks/use-product-context";
import { trainingKey, useTrainingMutation } from "@/hooks/use-training";
import {
  benchmarkRatios,
  benchmarkValues,
  benchmarkUsdInput,
  parseBenchmarkUsd,
} from "@/lib/workload-benchmark";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { OptionSelect } from "@/components/option-select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { ModelLabel } from "@/components/model-label";
import {
  OutcomeBar,
  RatioLabel,
} from "@/components/fine-tuning/evaluation-panel";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import { formatPercent } from "@/lib/format";

const muted = <span className="text-muted-foreground">—</span>;

// Cost and speed read as the comparison with the replacement, with the
// measured value in the tooltip; without a replacement, the value itself.
export const BenchmarkMetric = ({
  benchmark,
  metric,
}: {
  benchmark: WorkloadBenchmark;
  metric: "cost" | "speed";
}) => {
  const ratio = benchmarkRatios(benchmark)[metric];
  const value = benchmarkValues(benchmark)[metric];
  if (ratio) return <RatioLabel ratio={ratio} detail={value ?? ""} />;

  return value ? <span>{value}</span> : muted;
};

// Paired run outcomes as the better / same / worse bar; without them, the
// pass rates.
export const BenchmarkQuality = ({
  benchmark,
}: {
  benchmark: WorkloadBenchmark;
}) => {
  const quality = benchmark.quality;
  if (!quality) return muted;
  const rates = `${quality.metric}: ${formatPercent(quality.fine_tuned / 100)}${quality.comparison === null ? "" : ` vs ${formatPercent(quality.comparison / 100)}`}`;
  const outcome = quality.outcome;
  if (!outcome) return <span>{rates}</span>;
  const runs = outcome.better + outcome.same + outcome.worse;
  const share = (count: number) => formatPercent(count / runs);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="block w-40 cursor-default">
          <OutcomeBar
            outcome={{
              win: outcome.better / runs,
              tie: outcome.same / runs,
              loss: outcome.worse / runs,
              unresolved: 0,
            }}
            height="h-2"
            labels={false}
          />
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="text-xs">
        {benchmark.comparison_model_id
          ? `vs ${modelDisplayName(benchmark.comparison_model_id)}: `
          : null}
        better {share(outcome.better)} · same {share(outcome.same)} · worse{" "}
        {share(outcome.worse)} of {runs} runs
        <br />
        {rates}
      </TooltipContent>
    </Tooltip>
  );
};

export const WorkloadBenchmarkCard = ({
  task,
  versionId,
}: {
  task: string;
  versionId: string;
}) => {
  const query = useWorkloadBenchmark(task, versionId);
  const [editing, setEditing] = useState(false);
  const { canEdit } = useTrainingMutation(task);
  const { user } = useProductContext();
  const canManage = Boolean(
    canEdit &&
    ((user?.is_staff && user.email_verified) || user?.impersonated_by),
  );

  return (
    <section className="mb-5 rounded-lg border p-5">
      <div className="flex items-center justify-between gap-4">
        <h2 className="font-medium">Workload benchmarks</h2>
        {canManage ? (
          <Button
            variant="outline"
            size="sm"
            disabled={
              query.isFetching || Boolean(query.error && !query.invalid)
            }
            onClick={() => setEditing(true)}
          >
            Edit benchmarks
          </Button>
        ) : null}
      </div>
      {query.invalid ? (
        <p role="alert" className="mt-3 text-sm text-destructive">
          The saved benchmarks are not valid.
          {canManage ? " Edit them to replace the file." : null}
        </p>
      ) : query.error ? (
        <p role="alert" className="mt-3 text-sm text-destructive">
          Benchmarks could not be loaded.{" "}
          <button onClick={() => void query.retry()}>Retry</button>
        </p>
      ) : query.data ? (
        <div className="mt-4 grid gap-4 sm:grid-cols-4">
          {[
            [
              "Replaces",
              <ModelLabel key="model" id={query.data.comparison_model_id} />,
            ],
            [
              "Cost",
              <BenchmarkMetric
                key="cost"
                benchmark={query.data}
                metric="cost"
              />,
            ],
            [
              "Speed",
              <BenchmarkMetric
                key="speed"
                benchmark={query.data}
                metric="speed"
              />,
            ],
            [
              "Quality",
              <BenchmarkQuality key="quality" benchmark={query.data} />,
            ],
          ].map(([label, value]) => (
            <div key={String(label)}>
              <div className="text-xs text-muted-foreground">{label}</div>
              <div className="mt-1 flex min-h-6 items-center text-sm font-medium">
                {value}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">
          Add results from your workload evaluation.
        </p>
      )}
      {editing ? (
        <BenchmarkEditor
          task={task}
          versionId={versionId}
          initial={query.data}
          onClose={() => setEditing(false)}
        />
      ) : null}
    </section>
  );
};

const BenchmarkEditor = ({
  task,
  versionId,
  initial,
  onClose,
}: {
  task: string;
  versionId: string;
  initial: WorkloadBenchmark | undefined;
  onClose: () => void;
}) => {
  const query = useWorkloadBenchmark(task, versionId);
  const client = useQueryClient();
  const [values, setValues] = useState({
    workload: initial?.workload ?? "",
    comparison: initial?.comparison_model_id ?? "none",
    notes: initial?.notes ?? "",
    cost: benchmarkUsdInput(initial?.cost?.fine_tuned),
    comparisonCost: benchmarkUsdInput(initial?.cost?.comparison),
    speed: initial?.speed?.fine_tuned.toString() ?? "",
    comparisonSpeed: initial?.speed?.comparison?.toString() ?? "",
    quality: initial?.quality?.fine_tuned.toString() ?? "",
    comparisonQuality: initial?.quality?.comparison?.toString() ?? "",
    metric: initial?.quality?.metric ?? "Acceptance",
    samples: initial?.quality?.sample_size?.toString() ?? "",
    better: initial?.quality?.outcome?.better.toString() ?? "",
    same: initial?.quality?.outcome?.same.toString() ?? "",
    worse: initial?.quality?.outcome?.worse.toString() ?? "",
  });
  const [costUnit, setCostUnit] = useState<"task" | "1k_tokens">(
    initial?.cost?.unit ?? "task",
  );
  const [costBasis, setCostBasis] = useState<"measured" | "estimated">(
    initial?.cost?.basis ?? "measured",
  );
  const [speedUnit, setSpeedUnit] = useState<
    "latency_seconds" | "output_tokens_per_second"
  >(initial?.speed?.unit ?? "latency_seconds");
  const [statistic, setStatistic] = useState<"mean" | "median">(
    initial?.speed?.statistic ?? "median",
  );
  const numeric = (value: string) => (value.trim() ? Number(value) : null);
  const save = useMutation({
    mutationFn: async (reset: boolean) => {
      if (reset) {
        if (query.file)
          await deleteVersionFile({ ...query.path, file_id: query.file.id });
        return;
      }
      const benchmark = WorkloadBenchmarkSchema.parse({
        schema_version: 1,
        comparison_model_id:
          values.comparison === "none" ? null : values.comparison,
        workload: values.workload,
        notes: values.notes,
        cost: values.cost.trim()
          ? {
              unit: costUnit,
              fine_tuned: parseBenchmarkUsd(values.cost),
              comparison: parseBenchmarkUsd(values.comparisonCost),
              basis: costBasis,
            }
          : null,
        speed: values.speed.trim()
          ? {
              unit: speedUnit,
              fine_tuned: numeric(values.speed),
              comparison: numeric(values.comparisonSpeed),
              statistic,
            }
          : null,
        quality: values.quality.trim()
          ? {
              metric: values.metric,
              fine_tuned: numeric(values.quality),
              comparison: numeric(values.comparisonQuality),
              sample_size: numeric(values.samples),
              ...([values.better, values.same, values.worse].some((value) =>
                value.trim(),
              )
                ? {
                    outcome: {
                      better: numeric(values.better) ?? 0,
                      same: numeric(values.same) ?? 0,
                      worse: numeric(values.worse) ?? 0,
                    },
                  }
                : {}),
            }
          : null,
      });
      const body = new Blob([JSON.stringify(benchmark)], {
        type: "application/json",
      });
      const grant = await createVersionFile(query.path, {
        name: WORKLOAD_BENCHMARK_FILE,
        size_bytes: body.size,
        content_type: "application/json",
      });
      const response = await fetch(grant.upload_url, {
        method: "PUT",
        body,
        credentials: "omit",
      });
      if (!response.ok) throw new Error("Benchmark upload failed. Try again.");

      await completeVersionFile({ ...query.path, file_id: grant.id });
    },
    onSuccess: async () => {
      await client.invalidateQueries({
        queryKey: trainingKey(query.path.workspace_id),
      });
      onClose();
    },
  });
  const field = (key: keyof typeof values, label: string) => (
    <Label className="grid gap-2">
      {label}
      <Input
        value={values[key]}
        onChange={(event) =>
          setValues({ ...values, [key]: event.target.value })
        }
      />
    </Label>
  );

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !save.isPending) onClose();
      }}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit workload benchmarks</DialogTitle>
          <DialogDescription>
            Set the figures shown for this version. Leave unmeasured values
            blank. Costs are in USD.
          </DialogDescription>
        </DialogHeader>
        <form
          className="grid gap-5"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate(false);
          }}
        >
          {field("workload", "Workload")}
          <OptionSelect
            label="Replaces"
            value={values.comparison}
            onValueChange={(comparison) => setValues({ ...values, comparison })}
            options={[
              { value: "none", label: "No replacement model" },
              ...modelsForUseCase("comparison").map((model) => ({
                value: model.id,
                label: model.displayName,
              })),
            ]}
          />
          <fieldset className="grid gap-3 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">Cost</legend>
            <div className="grid grid-cols-2 gap-3">
              {field("cost", "This model ($)")}
              {field("comparisonCost", "Replacement ($, optional)")}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <OptionSelect
                label="Cost unit"
                value={costUnit}
                onValueChange={setCostUnit}
                options={[
                  { value: "task", label: "Per task" },
                  { value: "1k_tokens", label: "Per 1k tokens" },
                ]}
              />
              <OptionSelect
                label="Cost basis"
                value={costBasis}
                onValueChange={setCostBasis}
                options={[
                  { value: "measured", label: "Measured" },
                  { value: "estimated", label: "Estimated" },
                ]}
              />
            </div>
          </fieldset>
          <fieldset className="grid gap-3 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">Speed</legend>
            <div className="grid grid-cols-2 gap-3">
              {field("speed", "This model")}
              {field("comparisonSpeed", "Replacement (optional)")}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <OptionSelect
                label="Speed unit"
                value={speedUnit}
                onValueChange={setSpeedUnit}
                options={[
                  { value: "latency_seconds", label: "Latency (seconds)" },
                  {
                    value: "output_tokens_per_second",
                    label: "Output tokens/second",
                  },
                ]}
              />
              <OptionSelect
                label="Statistic"
                value={statistic}
                onValueChange={setStatistic}
                options={[
                  { value: "median", label: "Median" },
                  { value: "mean", label: "Mean" },
                ]}
              />
            </div>
          </fieldset>
          <fieldset className="grid gap-3 rounded-md border p-3">
            <legend className="px-1 text-sm font-medium">Quality</legend>
            {field("metric", "Metric name")}
            <div className="grid grid-cols-2 gap-3">
              {field("quality", "This model (%)")}
              {field("comparisonQuality", "Replacement (%, optional)")}
            </div>
            {field("samples", "Sample count (optional)")}
            <div className="grid grid-cols-3 gap-3">
              {field("better", "Runs better (optional)")}
              {field("same", "Runs the same")}
              {field("worse", "Runs worse")}
            </div>
          </fieldset>
          <Label className="grid gap-2">
            Notes
            <Textarea
              value={values.notes}
              onChange={(event) =>
                setValues({ ...values, notes: event.target.value })
              }
            />
          </Label>
          {save.error ? (
            <p role="alert" className="text-sm text-destructive">
              {save.error.message}
            </p>
          ) : null}
          <DialogFooter>
            {initial ? (
              <Button
                type="button"
                variant="ghost"
                disabled={save.isPending}
                onClick={() => save.mutate(true)}
              >
                Use automatic stats
              </Button>
            ) : null}
            <Button
              type="button"
              variant="outline"
              disabled={save.isPending}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save benchmarks"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
