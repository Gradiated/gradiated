import { ChevronDown, FlaskConical, MoreHorizontal } from "lucide-react";
import { useState } from "react";

import { UntrainedTaskState } from "@/components/fine-tuning/threshold-progress";
import { TrafficChart } from "@/components/fine-tuning/traffic-chart";
import {
  VersionActionButtons,
  VersionEvaluation,
  type VersionAction,
} from "@/components/fine-tuning/version-actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  STAGE_LABEL,
  isTerminalStage,
  type TaskRow,
  type VersionView,
} from "@/store/fine-tuning-types";
import { currentVersion } from "@/store/fine-tuning-views";
import {
  useTaskRuns,
  useTaskStats,
  useTaskVersions,
} from "@/store/mock-fine-tuning";

const VERSIONS_PAGE = 5;

const VERSION_MENU = [
  { kind: "promote", label: "Promote to production" },
  { kind: "use", label: "Use this version" },
  { kind: "download", label: "Download adapter" },
  { kind: "results", label: "View test results" },
] as const satisfies readonly { kind: VersionAction["kind"]; label: string }[];

const VersionMeta = ({ version }: { version: VersionView }) => (
  <>
    based on{" "}
    <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]">
      {version.model.base_model_id}
    </code>{" "}
    ·{" "}
    {new Date(version.model.created_at).toLocaleDateString(undefined, {
      dateStyle: "medium",
    })}{" "}
    · {version.run.dataset?.eligible_examples.toLocaleString() ?? "—"} traces
  </>
);

const VersionRow = ({
  version,
  open,
  onToggle,
  onAction,
}: {
  version: VersionView;
  open: boolean;
  onToggle: () => void;
  onAction: (action: VersionAction) => void;
}) => (
  <div className="border-b last:border-b-0">
    <div className="flex items-center justify-between gap-4 pr-5 hover:bg-muted/30">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex min-w-0 flex-1 items-center gap-3 py-3 pl-5 text-left"
      >
        <ChevronDown
          className={`size-4 shrink-0 text-muted-foreground transition-transform ${open ? "" : "-rotate-90"}`}
        />
        <div className="min-w-0">
          <span className="font-mono text-sm font-medium">
            {version.model.id}
          </span>
          <p className="mt-0.5 text-xs text-muted-foreground">
            <VersionMeta version={version} />
          </p>
        </div>
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-8 shrink-0"
            aria-label={`Actions for ${version.model.id}`}
          >
            <MoreHorizontal className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {VERSION_MENU.map((item) => (
            <DropdownMenuItem
              key={item.kind}
              onSelect={() =>
                onAction({ kind: item.kind, versionId: version.model.id })
              }
            >
              {item.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
    {open ? (
      <div className="border-t px-5 py-5">
        <VersionEvaluation version={version} onAction={onAction} />
      </div>
    ) : null}
  </div>
);

const CurrentVersion = ({
  task,
  version,
  onAction,
}: {
  task: TaskRow;
  version: VersionView;
  onAction: (action: VersionAction) => void;
}) => (
  <section className="rounded-xl border bg-card shadow-sm">
    <div className="flex items-start justify-between gap-4 px-5 py-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="font-mono text-lg font-semibold tracking-[-0.02em]">
            {version.is_production ? task.slug : version.model.id}
          </h2>
          {version.is_production ? (
            <Badge className="bg-[#6e7f31] text-white hover:bg-[#6e7f31]">
              Production
            </Badge>
          ) : (
            <Badge variant="outline" className="text-muted-foreground">
              Not in production
            </Badge>
          )}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {version.is_production ? (
            <>
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]">
                {version.model.id}
              </code>{" "}
              ·{" "}
            </>
          ) : null}
          <VersionMeta version={version} />
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {!version.is_production ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              onAction({ kind: "promote", versionId: version.model.id })
            }
          >
            Promote to production
          </Button>
        ) : null}
        <VersionActionButtons version={version} onAction={onAction} />
      </div>
    </div>
    <div className="border-t px-5 py-5">
      <VersionEvaluation version={version} onAction={onAction} />
    </div>
  </section>
);

export const TaskModelTab = ({
  task,
  onVersionAction,
  onShowRuns,
}: {
  task: TaskRow;
  onVersionAction: (action: VersionAction) => void;
  onShowRuns: () => void;
}) => {
  const versions = useTaskVersions(task.id);
  const runs = useTaskRuns(task.id);
  const { usable_traces_since_last_run: usableSinceLastRun } = useTaskStats(
    task.id,
  );
  const [openVersionId, setOpenVersionId] = useState<string | null>(null);
  const [versionsShown, setVersionsShown] = useState(VERSIONS_PAGE);

  const current = currentVersion(versions);
  const otherVersions = versions.filter((version) => version !== current);
  const activeRun = runs.find((run) => !isTerminalStage(run.stage));
  const hiddenVersions = otherVersions.length - versionsShown;

  return (
    <div className="space-y-5">
      {current ? (
        <>
          <CurrentVersion
            task={task}
            version={current}
            onAction={onVersionAction}
          />
          {otherVersions.length ? (
            <section>
              <h2 className="mb-2 text-sm font-medium">Other versions</h2>
              <div className="overflow-hidden rounded-lg border bg-card">
                {otherVersions.slice(0, versionsShown).map((version) => (
                  <VersionRow
                    key={version.model.id}
                    version={version}
                    open={openVersionId === version.model.id}
                    onToggle={() =>
                      setOpenVersionId((open) =>
                        open === version.model.id ? null : version.model.id,
                      )
                    }
                    onAction={onVersionAction}
                  />
                ))}
              </div>
              {hiddenVersions > 0 ? (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-2"
                  onClick={() =>
                    setVersionsShown((shown) => shown + VERSIONS_PAGE)
                  }
                >
                  Show {Math.min(VERSIONS_PAGE, hiddenVersions)} more
                </Button>
              ) : null}
            </section>
          ) : null}
        </>
      ) : (
        <UntrainedTaskState
          title="No model yet"
          icon={<FlaskConical className="size-5 text-muted-foreground" />}
          usableTraces={usableSinceLastRun}
          action={
            activeRun ? (
              <Button
                variant="link"
                size="sm"
                className="mt-1"
                onClick={onShowRuns}
              >
                First training run: {STAGE_LABEL[activeRun.stage].toLowerCase()}{" "}
                →
              </Button>
            ) : undefined
          }
        />
      )}
      <TrafficChart task={task} />
    </div>
  );
};
