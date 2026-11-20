import {
  catalogModel,
  type CatalogEntry,
} from "@gradiated/contracts/model-catalog";
import { useMutation } from "@tanstack/react-query";
import { ArrowUpRight, Download } from "lucide-react";
import { useState } from "react";

import { getAdapterDownload } from "@/api/training";
import { CodeSnippet } from "@/components/code-snippet";
import { CopyStateIcon } from "@/components/copy-state-icon";
import { ModelOption, modelOption } from "@/components/model-label";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { useProductContext } from "@/hooks/use-product-context";
import { formatFileSize } from "@/lib/format";
import type { VersionView } from "@/store/fine-tuning-types";

type Runtime = "vllm" | "sglang" | "peft";

const RUNTIMES = [
  { value: "vllm", label: "vLLM" },
  { value: "sglang", label: "SGLang" },
  { value: "peft", label: "PEFT" },
] as const;

// vLLM rejects --max-lora-rank values outside this list.
const VLLM_MAX_LORA_RANKS = [1, 8, 16, 32, 64, 128, 256, 320, 512];

const snippet = (
  runtime: Runtime,
  {
    name,
    repo,
    revision,
    rank,
  }: {
    name: string;
    repo: string;
    revision: string | undefined;
    rank: number;
  },
) => {
  const unpack = `mkdir ${name} && tar -xzf adapter.tar.gz -C ${name}`;
  const maxRank =
    VLLM_MAX_LORA_RANKS.find((allowed) => allowed >= rank) ?? rank;
  const pin = revision ? ` --revision ${revision}` : "";

  if (runtime === "vllm")
    return `${unpack}
vllm serve ${repo}${pin} \\
  --enable-lora --max-lora-rank ${maxRank} \\
  --lora-modules ${name}=./${name}`;

  if (runtime === "sglang")
    return `${unpack}
python -m sglang.launch_server --model-path ${repo}${pin} \\
  --enable-lora --max-lora-rank ${rank} \\
  --lora-paths ${name}=./${name}`;

  return `from peft import PeftModel
from transformers import AutoModelForCausalLM

base = AutoModelForCausalLM.from_pretrained(
    "${repo}"${revision ? `, revision="${revision}"` : ""}
)
model = PeftModel.from_pretrained(base, "./${name}")`;
};

const Detail = ({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) => (
  <div className={className}>
    <dt className="text-xs text-muted-foreground">{label}</dt>
    <dd className="mt-1">{children}</dd>
  </div>
);

export const DownloadAdapterDialog = ({
  version,
  onClose,
}: {
  version: VersionView;
  onClose: () => void;
}) => {
  const adapter = version.adapter;
  const { workspaceId } = useProductContext();
  const [runtime, setRuntime] = useState<Runtime>("vllm");
  const checksum = useCopyToClipboard();
  const repo =
    (catalogModel(version.base_model_id) as CatalogEntry | undefined)?.training
      ?.model ?? version.base_model_id;
  const revision =
    adapter.validated_base_model_revision ?? adapter.base_model_revision;
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
      <DialogContent
        className="max-h-[90dvh] grid-cols-[minmax(0,1fr)] overflow-y-auto sm:max-w-xl"
        onOpenAutoFocus={(event) => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Download {version.name}</DialogTitle>
          <DialogDescription>
            A standard PEFT LoRA adapter you can serve anywhere its base model
            runs.
          </DialogDescription>
        </DialogHeader>

        <dl className="grid grid-cols-4 gap-x-6 gap-y-3 border-t pt-4 text-sm">
          <Detail label="Base model" className="col-span-4 sm:col-span-2">
            <ModelOption {...modelOption(version.base_model_id)} />
          </Detail>
          <Detail label="Checkpoint" className="col-span-4 sm:col-span-2">
            {revision ? (
              <a
                href={`https://huggingface.co/${repo}/tree/${revision}`}
                target="_blank"
                rel="noreferrer"
                title={revision}
                className="inline-flex items-center gap-1 font-mono text-xs underline decoration-border underline-offset-4 hover:decoration-foreground"
              >
                {revision.slice(0, 12)}
                <ArrowUpRight aria-hidden className="size-3" />
              </a>
            ) : (
              <span className="text-muted-foreground">Unknown</span>
            )}
          </Detail>
          <Detail label={adapter.format === "cartridge" ? "Positions" : "Rank"}>
            <span className="tabular-nums">
              {adapter.format === "cartridge"
                ? adapter.num_tokens.toLocaleString()
                : adapter.rank}
            </span>
          </Detail>
          <Detail label="Size">
            <span className="tabular-nums">
              {formatFileSize(adapter.size_bytes)}
            </span>
          </Detail>
          <Detail label="SHA-256" className="col-span-2">
            <button
              type="button"
              title={adapter.sha256}
              aria-label="Copy SHA-256 checksum"
              onClick={() => void checksum.copy(adapter.sha256)}
              className="inline-flex max-w-full items-center gap-1.5 font-mono text-xs text-foreground hover:text-foreground/70"
            >
              <span className="truncate">{adapter.sha256.slice(0, 16)}</span>
              <CopyStateIcon
                state={checksum.state}
                className="size-3 shrink-0 text-muted-foreground"
              />
            </button>
          </Detail>
        </dl>

        {adapter.format === "cartridge" ? (
          <p className="text-xs text-muted-foreground">
            <span className="font-mono">cartridge.safetensors</span> holds the
            cartridge's learned input embeddings, which go in front of the
            system prompt.
          </p>
        ) : (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">
              <span className="font-mono">adapter.tar.gz</span> contains{" "}
              <span className="font-mono">adapter_config.json</span> and{" "}
              <span className="font-mono">adapter_model.safetensors</span>.
            </p>
            <CodeSnippet
              code={snippet(runtime, {
                name: version.name,
                repo,
                revision,
                rank: adapter.rank,
              })}
              language={runtime === "peft" ? "python" : "bash"}
              value={runtime}
              options={RUNTIMES}
              onValueChange={setRuntime}
              copyText="Copy command"
            />
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button
            disabled={download.isPending}
            onClick={() => download.mutate()}
          >
            <Download className="size-4" />
            {download.isPending ? "Preparing…" : "Download"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
