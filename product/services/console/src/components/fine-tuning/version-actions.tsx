import { EvaluationPanel } from "@/components/fine-tuning/evaluation-panel";
import { DownloadAdapterDialog } from "@/components/fine-tuning/download-adapter-dialog";
import { HoldoutResultsSheet } from "@/components/fine-tuning/holdout-results-sheet";
import { PromoteDialog } from "@/components/fine-tuning/promote-dialog";
import { UseModelDialog } from "@/components/fine-tuning/use-model-dialog";
import { Button } from "@/components/ui/button";
import type { TaskRow, VersionView } from "@/store/fine-tuning-types";
import { useTaskVersions } from "@/store/mock-fine-tuning";

export type VersionAction = Readonly<{
  kind: "use" | "download" | "results" | "promote";
  versionId: string;
}>;

export const VersionActionButtons = ({
  version,
  onAction,
}: {
  version: VersionView;
  onAction: (action: VersionAction) => void;
}) => (
  <>
    <Button
      variant="outline"
      size="sm"
      onClick={() =>
        onAction({ kind: "download", versionId: version.model.id })
      }
    >
      Download
    </Button>
    <Button
      size="sm"
      onClick={() => onAction({ kind: "use", versionId: version.model.id })}
    >
      Use
    </Button>
  </>
);

export const VersionEvaluation = ({
  version,
  onAction,
}: {
  version: VersionView;
  onAction: (action: VersionAction) => void;
}) => (
  <EvaluationPanel
    summary={version.summary}
    onViewResults={() =>
      onAction({ kind: "results", versionId: version.model.id })
    }
  />
);

export const VersionActionDialog = ({
  task,
  action,
  onClose,
}: {
  task: TaskRow;
  action: VersionAction;
  onClose: () => void;
}) => {
  const versions = useTaskVersions(task.id);
  const version = versions.find(
    (candidate) => candidate.model.id === action.versionId,
  );
  const production = versions.find((candidate) => candidate.is_production);

  if (!version) return null;

  switch (action.kind) {
    case "use":
      return (
        <UseModelDialog
          task={task}
          version={version}
          production={production}
          onClose={onClose}
        />
      );
    case "download":
      return <DownloadAdapterDialog version={version} onClose={onClose} />;
    case "results":
      return (
        <HoldoutResultsSheet task={task} version={version} onClose={onClose} />
      );
    case "promote":
      return (
        <PromoteDialog
          task={task}
          version={version}
          production={production}
          onClose={onClose}
        />
      );
  }
};
