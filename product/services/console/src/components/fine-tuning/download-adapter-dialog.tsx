import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import { useMutation } from "@tanstack/react-query";
import { getAdapterDownload } from "@/api/training";
import { useProductContext } from "@/hooks/use-product-context";
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
  const adapter = version.adapter;
  const { workspaceId } = useProductContext();
  const download = useMutation({
    mutationFn: () => getAdapterDownload(workspaceId, version.task, version.id),
    meta: { errorMessage: "The adapter could not be downloaded." },
    onSuccess: ({ url }) => {
      const link = document.createElement("a");
      link.href = url;
      link.referrerPolicy = "no-referrer";
      document.body.append(link);
      link.click();
      link.remove();
    },
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Download adapter</DialogTitle>
          <DialogDescription>
            The adapter is yours. It is a standard PEFT LoRA adapter for{" "}
            <span className="font-mono">
              {modelDisplayName(version.base_model_id)}
            </span>{" "}
            and runs anywhere that base runs: PEFT, vLLM with{" "}
            <span className="font-mono">--enable-lora</span>, or SGLang.
          </DialogDescription>
        </DialogHeader>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 rounded-lg border bg-muted/40 p-4 text-xs">
          <dt className="text-muted-foreground">Format</dt>
          <dd className="font-mono">
            {adapter.format} · adapter_config.json + adapter_model.safetensors
          </dd>
          <dt className="text-muted-foreground">Base model ID</dt>
          <dd className="font-mono">{version.base_model_id}</dd>
          <dt className="text-muted-foreground">Size</dt>
          <dd>
            {(adapter.size_bytes / MEBIBYTE).toFixed(1)} MB (rank {adapter.rank}
            )
          </dd>
        </dl>
        <DialogFooter>
          <Button
            disabled={download.isPending}
            onClick={() => download.mutate()}
          >
            <Download className="size-4" />
            {download.isPending ? "Preparing download…" : "adapter.tar.gz"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
