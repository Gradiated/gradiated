import { adapterProjectionShapes } from "@gradiated/contracts/adapter-shapes";
import { z } from "zod";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

// Module path (e.g. self_attn.q_proj) to the layer indices it appears in.
export type LayerModules = Map<string, Set<number>>;

export type BaseModelStructure = {
  layerCount: number;
  modules?: LayerModules;
};

const add = (modules: LayerModules, module: string, layer: number) => {
  const layers = modules.get(module) ?? new Set<number>();
  layers.add(layer);
  modules.set(module, layers);
};

// PEFT names tensors like base_model.model.model.layers.17.self_attn.q_proj.lora_A.weight.
export const adapterLayerModules = (tensorNames: string[]): LayerModules => {
  const modules: LayerModules = new Map();

  for (const name of tensorNames) {
    const match = /(?:^|\.)layers\.(\d+)\.(.+?)\.lora_[AB]\b/.exec(name);
    if (match?.[1] && match[2])
      add(
        modules,
        match[2].replace(/\.experts\.\d+\./, ".experts."),
        Number(match[1]),
      );
  }

  return modules;
};

export const baseModelStructure = (
  document: unknown,
): BaseModelStructure | undefined => {
  const parsed = z
    .object({ text_config: z.unknown().optional() })
    .passthrough()
    .safeParse(document);
  if (!parsed.success) return undefined;

  const config = parsed.data.text_config ?? parsed.data;
  const layers = z
    .object({ num_hidden_layers: z.number().int().min(1).max(4096) })
    .safeParse(config);
  if (!layers.success) return undefined;

  const shapes = adapterProjectionShapes(config);
  if (!shapes) return { layerCount: layers.data.num_hidden_layers };

  const modules: LayerModules = new Map();
  for (const key of Object.keys(shapes)) {
    const [layer, module] = key.split("/");
    if (layer && module) add(modules, module, Number(layer));
  }

  return { layerCount: layers.data.num_hidden_layers, modules };
};

const shortName = (module: string) => module.split(".").at(-1) ?? module;

export const AdapterLayerMap = ({
  adapted,
  base,
  loading = false,
}: {
  adapted: LayerModules;
  base?: BaseModelStructure | undefined;
  loading?: boolean;
}) => {
  if (loading)
    return (
      <div className="space-y-2">
        <span className="text-xs text-muted-foreground">Layers</span>
        <Skeleton className="h-24 w-full" />
      </div>
    );

  const modules = base?.modules;
  if (!base || !modules) return null;

  const layerCount = base.layerCount;
  const touched = new Set(
    [...adapted.values()].flatMap((layers) => [...layers]),
  ).size;

  const rows = [...new Set([...modules.keys(), ...adapted.keys()])];
  const labels = rows.map(shortName);
  const label = (index: number) =>
    labels.filter((name) => name === labels[index]).length > 1
      ? (rows[index] ?? "")
      : (labels[index] ?? "");

  return (
    <figure className="space-y-2">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-xs text-muted-foreground">Layers</span>
        <span className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="size-2 rounded-[2px] bg-[#6e7f31]" />
            Adapted
          </span>
          <span className="flex items-center gap-1">
            <span className="size-2 rounded-[2px] bg-muted-foreground/20" />
            Not adapted
          </span>
        </span>
      </figcaption>
      <div
        role="img"
        aria-label={`Adapter covers ${touched} of ${layerCount} layers`}
        className="grid items-center gap-y-[3px]"
        style={{
          gridTemplateColumns: `max-content repeat(${layerCount}, minmax(0, 1fr))`,
          columnGap: layerCount > 48 ? 0 : 1,
        }}
      >
        {rows.map((module, row) => {
          const present = modules.get(module);
          const covered = adapted.get(module);

          return [
            <span
              key={module}
              className="pr-3 font-mono text-[10px] leading-none text-muted-foreground"
            >
              {label(row)}
            </span>,
            ...Array.from({ length: layerCount }, (_, layer) => {
              const isAdapted = covered?.has(layer) ?? false;
              const exists = isAdapted || (present?.has(layer) ?? false);

              return (
                <span
                  key={`${module}-${layer}`}
                  title={`${module}, layer ${layer}: ${isAdapted ? "adapted" : exists ? "not adapted" : "not in this layer"}`}
                  className={cn(
                    "h-2.5",
                    layerCount <= 48 && "rounded-[1px]",
                    isAdapted
                      ? "bg-[#6e7f31]"
                      : exists && "bg-muted-foreground/20",
                  )}
                />
              );
            }),
          ];
        })}
        <span />
        <span
          className="mt-1 flex justify-between font-mono text-[10px] tabular-nums text-muted-foreground"
          style={{ gridColumn: `2 / span ${layerCount}` }}
        >
          <span>0</span>
          {layerCount > 2 ? (
            <span>{Math.floor((layerCount - 1) / 2)}</span>
          ) : null}
          <span>{layerCount - 1}</span>
        </span>
      </div>
    </figure>
  );
};
