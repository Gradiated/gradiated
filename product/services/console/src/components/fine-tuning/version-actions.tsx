import { useState } from "react";
import { EvaluationResultsDialog } from "./evaluation-results-dialog";
import { EvaluationPanel } from "@/components/fine-tuning/evaluation-panel";
import { DownloadAdapterDialog } from "@/components/fine-tuning/download-adapter-dialog";
import { PromoteDialog } from "@/components/fine-tuning/promote-dialog";
import { UseModelDialog } from "@/components/fine-tuning/use-model-dialog";
import { Button } from "@/components/ui/button";
import type { TaskRow, VersionView } from "@/store/fine-tuning-types";
import { useTaskHistory } from "@/hooks/use-training";

export type VersionAction = Readonly<{
  kind: "use" | "download" | "promote" | "results";
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
      onClick={() => onAction({ kind: "download", versionId: version.id })}
    >
      Download
    </Button>
    <Button
      size="sm"
      disabled={version.status !== "available"}
      title={
        version.status !== "available"
          ? "Serving is not enabled for this version."
          : undefined
      }
      onClick={() => onAction({ kind: "use", versionId: version.id })}
    >
      Use
    </Button>
  </>
);

export const VersionEvaluation = ({ version }: { version: VersionView }) => {
  const [showResults, setShowResults] = useState(false);

  return version.summary ? (
    <>
      <EvaluationPanel
        summary={version.summary}
        onViewResults={() => setShowResults(true)}
      />
      {showResults ? (
        <EvaluationResultsDialog
          version={version}
          onClose={() => setShowResults(false)}
        />
      ) : null}
    </>
  ) : (
    <p className="text-sm text-muted-foreground">
      {version.training_run_id
        ? "Evaluation not available yet."
        : "This adapter was uploaded externally. Evaluation results are not available."}
    </p>
  );
};

export const VersionActionDialog = ({
  task,
  action,
  onClose,
}: {
  task: TaskRow;
  action: VersionAction;
  onClose: () => void;
}) => {
  const versions = useTaskHistory(task).data?.versions ?? [];
  const version = versions.find(
    (candidate) => candidate.id === action.versionId,
  );
  const production = versions.find((candidate) => candidate.is_production);

  if (!version || (action.kind === "use" && version.status !== "available"))
    return null;

  switch (action.kind) {
    case "results":
      return <EvaluationResultsDialog version={version} onClose={onClose} />;
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
