import { CircleAlert } from "lucide-react";

import { DetailList, Stat, StatGrid } from "@/components/training/training-ui";
import {
  formatCost,
  formatCount,
  formatDuration,
  formatTokens,
} from "@/lib/grad/format";
import { formatShare } from "@/lib/grad/eval-report";
import type { PlanRunResponse } from "@/lib/grad/types";

export const PlanSummary = ({ plan }: { plan: PlanRunResponse }) => {
  const config = plan.resolvedConfig;
  const adapter =
    config.adapter.kind === "lora"
      ? `LoRA rank ${config.adapter.rank ?? "default"}`
      : config.adapter.kind.replaceAll("_", " ");

  return (
    <div className="space-y-5" aria-label="Plan" role="group">
      <StatGrid>
        <Stat
          label="Estimated cost"
          value={formatCost(plan.estimatedCostUsd)}
          detail={`${formatCost(plan.pricePerMillionTokens)} per million tokens`}
        />
        <Stat
          label="Tokens"
          value={formatTokens(plan.estimatedTokens)}
          detail={`${formatShare(plan.trainedTokenFraction)} trained`}
        />
        <Stat
          label="Steps"
          value={formatCount(plan.estimatedSteps)}
          detail={`${config.epochs} epoch${config.epochs === 1 ? "" : "s"}, batch ${config.batchSize}`}
        />
        <Stat
          label="Duration"
          value={`~${formatDuration(plan.estimatedDurationS)}`}
          detail="Excludes time in the queue"
        />
      </StatGrid>

      <DetailList
        items={[
          { label: "Base model", value: config.model },
          { label: "Adapter", value: adapter },
          {
            label: "Records",
            value: `${formatCount(plan.usableRecords)} of ${formatCount(plan.totalRecords)} usable`,
          },
          {
            label: "Split",
            value: `${formatCount(config.split.trainRecords)} train · ${formatCount(config.split.evalRecords)} held out`,
          },
          {
            label: "Learning rate",
            value: `${config.lr.toExponential(1)} (${config.lrSource})`,
          },
          {
            label: "Checkpoint selection",
            value: config.select === "best" ? "Best eval" : "Last step",
          },
          ...(plan.minGpuMemoryGb === null
            ? []
            : [{ label: "GPU memory", value: `${plan.minGpuMemoryGb} GB` }]),
          ...(plan.labeling
            ? [
                {
                  label: "Labeling before training",
                  value: formatCost(plan.labeling.estimatedCostUsd),
                },
              ]
            : []),
          ...(plan.teacher
            ? [
                {
                  label: `Teacher (${plan.teacher.model})`,
                  value: formatCost(plan.teacher.estimatedCostUsd),
                },
              ]
            : []),
        ]}
      />

      {plan.warnings.length ? (
        <ul className="space-y-2" aria-label="Plan warnings">
          {plan.warnings.map((warning) => (
            <li key={warning} className="flex gap-2 text-sm text-[#9a6a00]">
              <CircleAlert className="mt-0.5 size-4 shrink-0" />
              {warning}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
};
