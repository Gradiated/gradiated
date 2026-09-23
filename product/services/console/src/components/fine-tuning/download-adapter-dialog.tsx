import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { MEBIBYTE } from "@/store/fine-tuning-run-log";
import type { VersionView } from "@/store/fine-tuning-types";

export const DownloadAdapterDialog = ({
  version,
  onClose,
}: {
  version: VersionView;
  onClose: () => void;
}) => {
  const adapter = version.model.adapter;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
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
            {adapter.format} · adapter_config.json + adapter_model.safetensors
          </dd>
          <dt className="text-muted-foreground">Base model</dt>
          <dd className="font-mono">{version.model.base_model_id}</dd>
          <dt className="text-muted-foreground">Size</dt>
          <dd>
            {(adapter.size_bytes / MEBIBYTE).toFixed(0)} MB (rank {adapter.rank}
            , bf16)
          </dd>
        </dl>
        <DialogFooter>
          <Button variant="outline" disabled>
            <Download className="size-4" />
            manifest.json
          </Button>
          <Button disabled>
            <Download className="size-4" />
            adapter.tar.gz
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
