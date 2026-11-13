import { toast } from "sonner";

import { errorMessage } from "@/lib/errors";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { TaskRow, VersionView } from "@/store/fine-tuning-types";
import { usePrivateModelName } from "@/hooks/use-private-model-name";
import { useTrainingMutation } from "@/hooks/use-training";

export const PromoteDialog = ({
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
  const { promote, canEdit } = useTrainingMutation(task.name);
  const modelName = usePrivateModelName();

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Promote to production</DialogTitle>
          <DialogDescription>
            <span className="font-mono">{modelName(task.name)}</span> will point
            at <span className="font-mono">{version.name}</span>. Requests using
            it switch once the version is loaded.
            {production ? (
              <>
                {" "}
                <span className="font-mono">
                  {modelName(task.name, production.name)}
                </span>{" "}
                stays callable by its exact name.
              </>
            ) : null}
          </DialogDescription>
        </DialogHeader>
        {version.status !== "available" ? (
          <p className="text-sm text-muted-foreground">
            {promote.isPending
              ? "Loading the adapter on serving capacity and testing a request. This can take a minute."
              : "This version has not been served yet. Promoting first loads it on serving capacity and tests a request; production changes only if that succeeds."}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!canEdit || promote.isPending}
            onClick={() =>
              promote.mutate(version.id, {
                onSuccess: onClose,
                onError: (error) =>
                  toast.error(
                    errorMessage(error, "The version could not be promoted."),
                  ),
              })
            }
          >
            {promote.isPending
              ? version.status === "available"
                ? "Promoting…"
                : "Testing…"
              : "Promote"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
