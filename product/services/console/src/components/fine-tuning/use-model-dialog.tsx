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
import { usePrivateModelName } from "@/hooks/use-private-model-name";
import type { TaskRow, VersionView } from "@/store/fine-tuning-types";

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
  const modelName = usePrivateModelName();
  const id = version.is_production
    ? modelName(task.name)
    : modelName(task.name, version.name);
  const currentModel =
    production && production.id !== version.id
      ? modelName(task.name)
      : task.comparison_model_id;
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
                Adapters may load on first request, which can take longer than a
                warm request.
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
