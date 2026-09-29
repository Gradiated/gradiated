import { CopyStateIcon } from "@/components/copy-state-icon";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { copyLabel, useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import type { TaskRow, VersionView } from "@/store/fine-tuning-types";

const modelToReplace = (
  task: TaskRow,
  version: VersionView,
  production: VersionView | undefined,
) =>
  production && production.name !== version.name
    ? production.name
    : task.comparison_model_id;

export const UseModelDialog = ({
  task,
  version,
  production,
  onClose,
}: {
  task: TaskRow;
  version: VersionView;
  production: VersionView | undefined;
  onClose: () => void;
}) => {
  const id = version.is_production ? task.name : version.name;
  const currentModel = modelToReplace(task, version, production);
  const { state: copyState, copy } = useCopyToClipboard();

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-mono text-base">{id}</DialogTitle>
          <DialogDescription>
            Change the model string in your code.
            {version.is_production ? (
              <>
                {" "}
                <span className="font-mono">{id}</span> points at the production
                version, currently{" "}
                <span className="font-mono">{version.name}</span>.
              </>
            ) : (
              <>
                {" "}
                Versions that are not in production load on first request; allow
                up to a minute.
              </>
            )}
          </DialogDescription>
        </DialogHeader>
        <pre className="overflow-x-auto rounded-lg border bg-muted p-4 font-mono text-xs leading-6">
          <div className="text-destructive">
            <span className="select-none">- </span>model: "{currentModel}"
          </div>
          <div className="text-emerald-700">
            <span className="select-none">+ </span>model: "{id}"
          </div>
        </pre>
        <DialogFooter>
          <Button variant="outline" onClick={() => void copy(id)}>
            <CopyStateIcon state={copyState} className="size-4" />
            {copyLabel(copyState, "Copy model id")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
