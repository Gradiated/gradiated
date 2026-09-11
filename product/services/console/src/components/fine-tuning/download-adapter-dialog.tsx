import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { VersionView } from "@/store/mock-fine-tuning";

/** POST P/tasks/{task_id}/models/{model_id}/export is called when a button is clicked. */
export const DownloadAdapterDialog = ({
  version,
  trigger,
  open,
  onOpenChange,
}: {
  version: VersionView;
  trigger?: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) => {
  const adapter = version.model.adapter;
  return (
    <Dialog
      {...(open !== undefined ? { open } : {})}
      {...(onOpenChange ? { onOpenChange } : {})}
    >
      {trigger ? <DialogTrigger asChild>{trigger}</DialogTrigger> : null}
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Download adapter</DialogTitle>
          <DialogDescription>
            The adapter is yours. It is a standard PEFT LoRA adapter for{" "}
            <span className="font-mono">{version.model.base_model_id}</span> and
            runs anywhere that base runs — PEFT, vLLM with{" "}
            <span className="font-mono">--enable-lora</span>, or SGLang.
          </DialogDescription>
        </DialogHeader>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 rounded-lg border bg-muted/40 p-4 text-xs">
          <dt className="text-muted-foreground">Format</dt>
          <dd className="font-mono">
            {adapter?.format ?? "peft_lora"} · adapter_config.json +
            adapter_model.safetensors
          </dd>
          <dt className="text-muted-foreground">Base model</dt>
          <dd className="font-mono">{version.model.base_model_id}</dd>
          <dt className="text-muted-foreground">Size</dt>
          <dd>
            {adapter
              ? `${(adapter.size_bytes / 1_048_576).toFixed(0)} MB`
              : "—"}{" "}
            (rank {adapter?.rank ?? "—"}, bf16)
          </dd>
          <dt className="text-muted-foreground">Manifest</dt>
          <dd>
            base revision, tokenizer hash, hyperparameters, dataset hashes,
            per-file sha256
          </dd>
        </dl>
        <DialogFooter>
          <Button variant="outline">
            <Download className="size-4" />
            manifest.json
          </Button>
          <Button>
            <Download className="size-4" />
            adapter.tar.gz
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
