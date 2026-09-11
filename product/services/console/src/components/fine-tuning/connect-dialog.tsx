import { ConnectSnippet } from "@/components/fine-tuning/connect-snippet";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export const ConnectDialog = ({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>Train a model</DialogTitle>
        <DialogDescription>
          Point your OpenAI or Anthropic traffic at Gradiated. You keep your
          provider key.
        </DialogDescription>
      </DialogHeader>
      <ConnectSnippet />
    </DialogContent>
  </Dialog>
);
