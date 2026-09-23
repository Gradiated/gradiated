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
import { useMockFineTuning } from "@/store/mock-fine-tuning";

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
  const promote = useMockFineTuning((state) => state.promote);

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Promote to production</DialogTitle>
          <DialogDescription>
            <span className="font-mono">{task.slug}</span> will point at{" "}
            <span className="font-mono">{version.model.id}</span>. Requests
            using the task name switch once it is loaded.
            {production ? (
              <>
                {" "}
                <span className="font-mono">{production.model.id}</span> stays
                callable by its exact id.
              </>
            ) : null}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              promote(task.id, version.model.id);
              onClose();
            }}
          >
            Promote
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
