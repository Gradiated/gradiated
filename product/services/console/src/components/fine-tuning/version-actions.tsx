import { EvaluationPanel } from "@/components/fine-tuning/evaluation-panel";
import { DownloadAdapterDialog } from "@/components/fine-tuning/download-adapter-dialog";
import { PromoteDialog } from "@/components/fine-tuning/promote-dialog";
import { UseModelDialog } from "@/components/fine-tuning/use-model-dialog";
import { Button } from "@/components/ui/button";
import type { TaskRow, VersionView } from "@/store/fine-tuning-types";
import { useTaskHistory } from "@/hooks/use-training";

export type VersionAction = Readonly<{
  kind: "use" | "download" | "promote";
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
      onClick={() => onAction({ kind: "use", versionId: version.id })}
    >
      Use
    </Button>
  </>
);

export const VersionEvaluation = ({ version }: { version: VersionView }) =>
  version.summary ? (
    <EvaluationPanel summary={version.summary} />
  ) : (
    <p className="text-sm text-muted-foreground">
      Evaluation not available yet.
    </p>
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
  const versions = useTaskHistory(task).data?.versions ?? [];
  const version = versions.find(
    (candidate) => candidate.id === action.versionId,
  );
  const production = versions.find((candidate) => candidate.is_production);

  if (!version || (action.kind === "use" && version.status !== "available"))
    return null;

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
