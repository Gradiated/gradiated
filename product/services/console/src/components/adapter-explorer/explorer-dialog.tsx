import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useQueryClient } from "@tanstack/react-query";
import { Layers, X } from "lucide-react";
import { lazy, Suspense, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ExplorerLoading } from "./loading";
import { adapterWeightsQuery, type ExplorerTarget } from "./queries";

const loadExplorer = () => import("./explorer");
const AdapterExplorer = lazy(loadExplorer);

export const AdapterExplorerButton = ({
  target,
  title,
  baseModelId,
}: {
  target: ExplorerTarget;
  title: string;
  baseModelId: string;
}) => {
  const [open, setOpen] = useState(false);
  const escape = useRef<() => boolean>(() => false);
  const client = useQueryClient();
  const warm = () => {
    void loadExplorer();
    void client.prefetchQuery(adapterWeightsQuery(target));
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>
        <Button variant="outline" onPointerEnter={warm} onFocus={warm}>
          <Layers className="size-4" />
          Explore weights
        </Button>
      </DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          onEscapeKeyDown={(event) => {
            if (escape.current()) event.preventDefault();
          }}
          className="fixed inset-2 z-50 overflow-hidden rounded-2xl border border-white/10 bg-[#030508] outline-none sm:inset-4"
        >
          <DialogPrimitive.Title className="sr-only">
            {title} adapter explorer
          </DialogPrimitive.Title>
          <Suspense fallback={<ExplorerLoading message="Loading explorer" />}>
            <AdapterExplorer
              target={target}
              title={title}
              baseModelId={baseModelId}
              escape={escape}
            />
          </Suspense>
          <DialogPrimitive.Close className="absolute right-3 top-3 z-20 grid size-9 place-items-center rounded-full border border-white/10 bg-black/40 text-white/70 backdrop-blur hover:bg-white/10 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-lime-300/60">
            <X className="size-4" />
            <span className="sr-only">Close</span>
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};
