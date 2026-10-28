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

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Promote to production</DialogTitle>
          <DialogDescription>
            <span className="font-mono">{task.name}</span> will point at{" "}
            <span className="font-mono">{version.name}</span>. Requests using
            the task name switch once it is loaded.
            {production ? (
              <>
                {" "}
                <span className="font-mono">{production.name}</span> stays
                callable by its exact id.
              </>
            ) : null}
          </DialogDescription>
        </DialogHeader>
        {version.status !== "available" ? (
          <p className="text-sm text-muted-foreground">
            Serving is not enabled for this version.
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={
              !canEdit || promote.isPending || version.status !== "available"
            }
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
            Promote
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
