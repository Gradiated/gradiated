import { Check, Copy } from "lucide-react";
import { useState } from "react";

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

/**
 * "Use" only shows the one-line code change. `modelId` defaults to the exact
 * version id; pass the task name to show the string that resolves to the
 * production version (SERV-03).
 */
export const UseModelDialog = ({
  version,
  modelId,
  currentModel,
  trigger,
  open,
  onOpenChange,
}: {
  version: VersionView;
  modelId?: string;
  currentModel: string;
  trigger?: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) => {
  const id = modelId ?? version.model.id;
  const isTaskName = id !== version.model.id;
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(id);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <Dialog
      {...(open !== undefined ? { open } : {})}
      {...(onOpenChange ? { onOpenChange } : {})}
    >
      {trigger ? <DialogTrigger asChild>{trigger}</DialogTrigger> : null}
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-mono text-base">{id}</DialogTitle>
          <DialogDescription>
            Change the model string in your code.
            {isTaskName ? (
              <>
                {" "}
                <span className="font-mono">{id}</span> points at the production
                version, currently{" "}
                <span className="font-mono">{version.model.id}</span>.
              </>
            ) : (
              <>
                {" "}
                Versions that are not in production load on first request; allow
                up to a minute.
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
          <Button variant="outline" onClick={copy}>
            {copied ? (
              <Check className="size-4" />
            ) : (
              <Copy className="size-4" />
            )}
            {copied ? "Copied" : "Copy model id"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
