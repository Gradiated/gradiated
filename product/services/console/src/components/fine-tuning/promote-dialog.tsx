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
        {promote.error ? (
          <p role="alert" className="text-sm text-destructive">
            {promote.error.message}
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
            onClick={() => promote.mutate(version.id, { onSuccess: onClose })}
          >
            Promote
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
