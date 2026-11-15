import { useQuery } from "@tanstack/react-query";
import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import { Crosshair } from "lucide-react";

import { ModelLabel } from "@/components/model-label";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";

import { buildDeckLayout, type DeckLayout, type PlateLayout } from "./layout";
import { ExplorerLoading } from "./loading";
import {
  buildExplorerModel,
  formatCount,
  formatShape,
  heatColor,
  heatRgb,
  type AdapterWeights,
  type BaseStructure,
  type ExplorerModel,
  type Heatmap,
  type ModuleView,
} from "./model";
import {
  adapterWeightsQuery,
  baseStructureQuery,
  type ExplorerTarget,
} from "./queries";
import { ExplorerScene, webglAvailable, type Pick } from "./scene";

type ExplorerProps = {
  target: ExplorerTarget;
  title: string;
  baseModelId: string;
  escape: RefObject<() => boolean>;
};

const AdapterExplorer = (props: ExplorerProps) => {
  const weights = useQuery(adapterWeightsQuery(props.target));
  const structure = useQuery(baseStructureQuery(props.target));

  if (weights.isPending || structure.isPending)
    return (
      <ExplorerLoading
        message={
          weights.isPending ? "Reading adapter weights" : "Loading model layout"
        }
      />
    );

  if (weights.isError)
    return (
      <div className="grid h-full place-items-center bg-[#030508] p-6 text-white">
        <div className="flex max-w-sm flex-col items-center gap-3 text-center">
          <p className="font-medium">The adapter weights could not be read.</p>
          <p className="text-sm text-white/55">
            {weights.error instanceof Error
              ? weights.error.message
              : "Please try again."}
          </p>
          <button
            type="button"
            onClick={() => void weights.refetch()}
            className="mt-2 rounded-full border border-white/15 px-4 py-1.5 text-sm hover:bg-white/10"
          >
            {weights.isFetching ? "Retrying…" : "Try again"}
          </button>
        </div>
      </div>
    );

  return (
    <ExplorerStage
      {...props}
      weights={weights.data}
      structure={structure.data}
    />
  );
};

export default AdapterExplorer;

const plateTitle = (plate: PlateLayout) =>
  plate.kind === "embedding"
    ? "Embedding"
    : plate.kind === "head"
      ? "Output head"
      : `Layer ${plate.layer}`;

const moduleTitle = (module: ModuleView) =>
  module.layer === null ? "Output head" : `Layer ${module.layer}`;

const percent = (value: number) =>
  value <= 0
    ? "0%"
    : value < 0.001
      ? "<0.1%"
      : `${(value * 100).toFixed(value < 0.1 ? 1 : 0)}%`;

const ExplorerStage = ({
  weights,
  structure,
  title,
  baseModelId,
  escape,
}: ExplorerProps & {
  weights: AdapterWeights;
  structure: BaseStructure | undefined;
}) => {
  const model = useMemo(
    () => buildExplorerModel(weights, structure),
    [weights, structure],
  );
  const layout = useMemo(() => buildDeckLayout(model), [model]);
  const host = useRef<HTMLDivElement>(null);
  const tooltip = useRef<HTMLDivElement>(null);
  const scene = useRef<ExplorerScene | null>(null);
  const [hover, setHover] = useState<Pick | null>(null);
  const [focus, setFocus] = useState<number | null>(null);
  const [selection, setSelection] = useState<ModuleView | null>(null);
  const [touring, setTouring] = useState(false);
  const [unsupported, setUnsupported] = useState(false);
  const reducedMotion = useMemo(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    [],
  );

  const choose = useCallback((pick: Pick | null) => {
    if (!pick) return;

    setSelection(pick.kind === "module" ? pick.module : null);
    setFocus(pick.plate);
    scene.current?.select(pick.kind === "module" ? pick.module.index : null);
    scene.current?.focus(pick.plate);
  }, []);
  const overview = useCallback(() => {
    scene.current?.stopTour();
    scene.current?.select(null);
    scene.current?.focus(null);
    setSelection(null);
    setFocus(null);
  }, []);

  useEffect(() => {
    const element = host.current;
    if (!element) return;

    if (!webglAvailable()) {
      setUnsupported(true);
      return;
    }
    const wide = window.matchMedia("(min-width: 768px)");
    const insetFor = () => (wide.matches ? 316 : 0);
    let instance: ExplorerScene;
    try {
      instance = new ExplorerScene(
        element,
        model,
        layout,
        {
          hover: setHover,
          select: choose,
          tour: setTouring,
          interact: () => {},
        },
        reducedMotion,
        insetFor(),
      );
    } catch {
      setUnsupported(true);
      return;
    }
    scene.current = instance;
    const inset = () => instance.setInset(insetFor());
    wide.addEventListener("change", inset);
    return () => {
      wide.removeEventListener("change", inset);
      instance.dispose();
      scene.current = null;
    };
  }, [model, layout, reducedMotion, choose]);

  const state = useRef({ focus, touring });
  state.current = { focus, touring };
  useEffect(() => {
    escape.current = () => {
      if (state.current.focus === null && !state.current.touring) return false;

      overview();
      return true;
    };
    return () => {
      escape.current = () => false;
    };
  }, [escape, overview]);

  // The dialog is modal, so arrow keys step layers wherever focus is inside it.
  const focusRef = useRef(focus);
  focusRef.current = focus;
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const direction =
        event.key === "ArrowRight" || event.key === "ArrowDown"
          ? 1
          : event.key === "ArrowLeft" || event.key === "ArrowUp"
            ? -1
            : 0;
      if (!direction) return;

      event.preventDefault();
      const plates = layout.plates.length;
      const current = focusRef.current;
      const next =
        current === null
          ? direction > 0
            ? 0
            : plates - 1
          : Math.min(plates - 1, Math.max(0, current + direction));
      choose({ kind: "plate", plate: next });
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [layout, choose]);

  return (
    <div
      className="relative h-full w-full overflow-hidden bg-[#030508] text-white"
      onPointerMove={(event) => {
        const element = tooltip.current;
        if (!element) return;

        const bounds = event.currentTarget.getBoundingClientRect();
        const x = event.clientX - bounds.left;
        const y = event.clientY - bounds.top;
        const flip = x > bounds.width - 300;
        element.style.transform = `translate(${flip ? x - 14 : x + 16}px, ${y + 16}px) translateX(${flip ? "-100%" : "0"})`;
      }}
    >
      <div
        ref={host}
        className="absolute inset-0"
        role="img"
        aria-label={`3D view of ${modelDisplayName(baseModelId)}: ${model.layerCount} layers, with the projections this adapter changes lit by how much they change. Use the arrow keys or the layer strip to move between layers.`}
      />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-[#030508] via-[#030508]/70 to-transparent" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#030508] via-[#030508]/60 to-transparent" />

      {unsupported ? (
        <div className="absolute inset-0 grid place-items-center p-6 text-center">
          <p className="max-w-sm text-sm text-white/60">
            The 3D view needs WebGL 2, which is unavailable in this browser. The
            layer strip and inspector still show the full summary.
          </p>
        </div>
      ) : null}

      <header className="pointer-events-none absolute left-4 right-16 top-4 flex flex-col gap-2 sm:left-6 sm:top-5">
        <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
          {title}
        </h2>
      </header>

      <div className="absolute right-14 top-3 z-10 flex gap-2">
        {focus !== null ? (
          <HudButton onClick={overview}>
            <Crosshair className="size-3.5" />
            Overview
          </HudButton>
        ) : null}
      </div>

      <aside className="absolute bottom-[5.5rem] right-3 top-[4.25rem] hidden w-[18.5rem] overflow-y-auto rounded-2xl border border-white/10 bg-black/45 p-4 backdrop-blur-md [scrollbar-width:thin] md:block">
        {selection ? (
          <ModulePanel module={selection} />
        ) : focus !== null ? (
          <PlatePanel
            plate={layout.plates[focus]!}
            onSelect={(module) =>
              choose({ kind: "module", plate: focus, module })
            }
          />
        ) : (
          <OverviewPanel model={model} baseModelId={baseModelId} />
        )}
      </aside>

      <LayerStrip
        model={model}
        layout={layout}
        focus={focus}
        onChoose={(plate) => choose({ kind: "plate", plate })}
      />

      <div
        ref={tooltip}
        className="pointer-events-none absolute left-0 top-0 z-20 will-change-transform"
      >
        {hover ? (
          <HoverCard pick={hover} model={model} layout={layout} />
        ) : null}
      </div>
    </div>
  );
};

const HudButton = ({
  onClick,
  children,
}: {
  onClick: () => void;
  children: ReactNode;
}) => (
  <button
    type="button"
    onClick={onClick}
    className="inline-flex h-9 items-center gap-1.5 rounded-full border border-white/10 bg-black/40 px-3.5 text-xs font-medium text-white/80 backdrop-blur transition-colors hover:bg-white/10 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-lime-300/60"
  >
    {children}
  </button>
);

const LayerStrip = ({
  model,
  layout,
  focus,
  onChoose,
}: {
  model: ExplorerModel;
  layout: DeckLayout;
  focus: number | null;
  onChoose: (plate: number) => void;
}) => (
  <nav
    aria-label="Layers"
    className="absolute bottom-3 left-3 right-3 rounded-2xl border border-white/10 bg-black/45 px-3 pb-2 pt-2.5 backdrop-blur-md md:right-[20.5rem]"
  >
    <div className="flex h-10 items-end gap-px">
      {layout.plates.map((plate) => {
        const layer =
          plate.kind === "layer" ? model.layers[plate.layer!] : undefined;
        const share =
          plate.kind === "head"
            ? (model.head?.share ?? 0)
            : (layer?.share ?? 0);
        const intensity = plate.intensity;
        const changed = share > 0;
        return (
          <button
            key={plate.index}
            type="button"
            onClick={() => onChoose(plate.index)}
            aria-label={`${plateTitle(plate)}: ${changed ? `${percent(share)} of the change` : "unchanged"}`}
            aria-current={focus === plate.index ? "true" : undefined}
            title={`${plateTitle(plate)} · ${changed ? `${percent(share)} of the change` : "unchanged"}`}
            className={`group relative flex h-full min-w-0 flex-1 items-end justify-center rounded-[3px] focus:outline-none focus-visible:ring-1 focus-visible:ring-lime-300 ${plate.kind !== "layer" ? "max-w-6 basis-6" : ""} ${focus === plate.index ? "bg-white/15" : "hover:bg-white/10"}`}
          >
            <span
              className="w-full rounded-[2px] transition-[height] duration-500"
              style={{
                height: `${changed ? 18 + intensity * 82 : 10}%`,
                background: changed
                  ? heatColor(0.3 + 0.7 * intensity)
                  : "rgba(148,170,196,0.18)",
                boxShadow: changed
                  ? `0 0 ${4 + intensity * 10}px ${heatColor(0.4 + 0.6 * intensity)}`
                  : undefined,
              }}
            />
          </button>
        );
      })}
    </div>
    <div className="mt-1.5 flex justify-between text-xs text-white/40">
      <span>Layers</span>
      <span>
        {focus !== null ? plateTitle(layout.plates[focus]!) : "← → to step"}
      </span>
    </div>
  </nav>
);

const HoverCard = ({
  pick,
  model,
  layout,
}: {
  pick: Pick;
  model: ExplorerModel;
  layout: DeckLayout;
}) => {
  const plate = layout.plates[pick.plate]!;
  let heading = plateTitle(plate);
  let lines: string[] = [];
  let tone = 0;
  if (pick.kind === "module") {
    const { module } = pick;
    heading = `${moduleTitle(module)} · ${module.label}`;
    tone = module.adapted ? module.intensity : 0;
    lines = module.adapted
      ? [
          `${formatShape(module.shape)}${module.experts > 1 ? ` · ${module.experts} experts` : ""}`,
          `${percent(module.share)} of the change`,
        ]
      : ["Unchanged by this adapter"];
  } else if (pick.kind === "expert") {
    heading = `${plateTitle(plate)} · expert ${pick.expert}`;
    const adapted = model.modules.some(
      (module) =>
        module.layer === plate.layer &&
        module.group === "experts" &&
        module.adapted,
    );
    lines = [
      `Routed expert ${pick.expert + 1} of ${plate.experts?.count ?? 0}`,
      adapted ? "Changed by this adapter" : "Unchanged by this adapter",
    ];
  } else if (plate.kind === "layer") {
    const layer = model.layers[plate.layer!]!;
    const adapted = layer.modules.filter((module) => module.adapted).length;
    tone = layer.share > 0 ? layer.intensity : 0;
    lines =
      layer.share > 0
        ? [
            `${percent(layer.share)} of the change`,
            `${adapted} of ${layer.modules.length} projections adapted`,
          ]
        : ["Unchanged by this adapter"];
  } else if (plate.kind === "head") {
    tone = model.head?.adapted ? model.head.intensity : 0;
    lines = model.head?.adapted
      ? [`${percent(model.head.share)} of the change`]
      : ["Unchanged by this adapter"];
  } else lines = ["Token embeddings · unchanged"];

  return (
    <div className="min-w-48 max-w-72 rounded-xl border border-white/10 bg-black/70 px-3 py-2 shadow-xl backdrop-blur-md">
      <p className="flex items-center gap-2 text-xs font-semibold">
        <span
          className="size-2 shrink-0 rounded-full"
          style={{
            background: tone
              ? heatColor(0.3 + 0.7 * tone)
              : "rgba(148,170,196,0.35)",
          }}
        />
        {heading}
      </p>
      {lines.map((line) => (
        <p key={line} className="mt-0.5 font-mono text-[11px] text-white/60">
          {line}
        </p>
      ))}
    </div>
  );
};

const Section = ({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) => (
  <section className="flex flex-col gap-2.5 border-t border-white/10 mt-4 pt-4 first:mt-0 first:border-t-0 first:pt-0">
    <h3 className="text-xs font-semibold uppercase tracking-wide text-white/50">
      {title}
    </h3>
    {children}
  </section>
);

const Fact = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="flex items-baseline justify-between gap-4 text-sm">
    <dt className="shrink-0 text-white/50">{label}</dt>
    <dd className="min-w-0 truncate text-right text-white/90">{children}</dd>
  </div>
);

const OverviewPanel = ({
  model,
  baseModelId,
}: {
  model: ExplorerModel;
  baseModelId: string;
}) => (
  <>
    <Section title="Model">
      <ModelLabel
        id={baseModelId}
        className="text-sm text-white/90"
        iconClassName="invert"
      />
      <dl className="flex flex-col gap-2">
        <Fact label="Layers">{model.layerCount}</Fact>
        {model.expertCount ? (
          <Fact label="Experts per layer">{model.expertCount}</Fact>
        ) : null}
      </dl>
    </Section>
    <Section title="Adapter">
      <dl className="flex flex-col gap-2">
        <Fact label="Trained parameters">{formatCount(model.parameters)}</Fact>
      </dl>
    </Section>
  </>
);

const PlatePanel = ({
  plate,
  onSelect,
}: {
  plate: PlateLayout;
  onSelect: (module: ModuleView) => void;
}) => {
  const changed = plate.panels
    .map((panel) => panel.module)
    .filter((module) => module.adapted);
  return (
    <Section title={plateTitle(plate)}>
      {changed.length ? (
        <div className="-mx-2 flex flex-col">
          {changed.map((module) => (
            <button
              key={module.index}
              type="button"
              onClick={() => onSelect(module)}
              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-white/85 hover:bg-white/[0.06] focus:outline-none focus-visible:ring-1 focus-visible:ring-white/40"
            >
              <span
                className="size-2 shrink-0 rounded-full"
                style={{ background: heatColor(0.3 + 0.7 * module.intensity) }}
              />
              <span className="truncate font-mono text-xs">{module.label}</span>
            </button>
          ))}
        </div>
      ) : (
        <p className="text-sm text-white/50">Unchanged by this adapter.</p>
      )}
    </Section>
  );
};

const ModulePanel = ({ module }: { module: ModuleView }) => {
  const head = module.group === "head";
  return (
    <Section title={`${moduleTitle(module)} · ${module.label}`}>
      {module.adapted && module.heatmap ? (
        <>
          <HeatmapView
            heatmap={module.heatmap}
            rows={head ? "Vocabulary" : "Outputs"}
            columns={head ? "Hidden size" : "Inputs"}
            shape={module.shape}
          />
          <p className="text-xs text-white/50">
            Each cell is a block of the weight matrix. Brighter blocks changed
            more.
          </p>
        </>
      ) : (
        <p className="text-sm text-white/50">Unchanged by this adapter.</p>
      )}
    </Section>
  );
};

const HeatmapView = ({
  heatmap,
  rows,
  columns,
  shape,
}: {
  heatmap: Heatmap;
  rows: string;
  columns: string;
  shape: readonly [number, number];
}) => {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;

    element.width = heatmap.columns;
    element.height = heatmap.rows;
    const image = context.createImageData(heatmap.columns, heatmap.rows);
    heatmap.values.forEach((value, index) => {
      const [red, green, blue] = heatRgb(0.08 + 0.92 * (value / 255));
      image.data.set([red, green, blue, 255], index * 4);
    });
    context.putImageData(image, 0, 0);
  }, [heatmap]);
  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1">
      <span className="rotate-180 self-center text-[11px] text-white/40 [writing-mode:vertical-rl]">
        {rows} · {shape[0].toLocaleString("en-US")}
      </span>
      <canvas
        ref={canvas}
        className="max-h-72 w-full rounded-md border border-white/10 [image-rendering:pixelated]"
        style={{ aspectRatio: `${heatmap.columns} / ${heatmap.rows}` }}
      />
      <span className="col-start-2 text-center text-[11px] text-white/40">
        {columns} · {shape[1].toLocaleString("en-US")}
      </span>
    </div>
  );
};
