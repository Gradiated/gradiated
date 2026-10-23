import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { CSSProperties } from "react";
import { siliconColours } from "./materials";
import { CleanRoom, WholeWafer } from "./FabricationLab";
import { PatterningModel, patterningCamera } from "./PatterningModel";
import { WaferMagnification } from "./WaferMagnification";
import {
  blendPattern,
  inverterDuration,
  inverterOperation,
  patternState,
  patternSurfaceHeight,
  portion,
  sceneDuration,
  stages,
  visitFor,
} from "./process";
import type { PatternState } from "./process";
import type { CameraState } from "./PatterningModel";
import { groups, introduction, machines, scenes } from "./model";
import type { MachineId } from "./model";
import { maskCycles } from "./sequence";
import "./fabrication.css";

type Presentation = { material: PatternState; camera: CameraState };
const initialPresentation: Presentation = {
  material: patternState(0, visitFor(1, undefined, undefined)),
  camera: { elevation: 0.62, section: 0 },
};

export const FabricationJourney = () => {
  const host = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLElement>(null);
  const roomRef = useRef<HTMLDivElement>(null);
  const sections = useRef<(HTMLElement | null)[]>([]);
  const openTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const closeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const pinnedPreview = useRef(false);
  const [active, setActive] = useState(0);
  const [animation, setAnimation] = useState({
    index: 0,
    progress: 1,
    from: initialPresentation,
  });
  const displayed = useRef<Presentation>(initialPresentation);
  const previousScene = useRef(0);
  const [fromMachine, setFromMachine] = useState<MachineId>();
  const [fromIndex, setFromIndex] = useState(1);
  const [input, setInput] = useState(0);
  const [preview, setPreview] = useState<MachineId | undefined>();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [replay, setReplay] = useState(0);
  const progress = reduced
    ? 1
    : animation.index === active
      ? animation.progress
      : 0;
  const inverter = active === 0 || active === stages.inverter;
  const electrical = inverterOperation(input, progress);
  const step = scenes[active];
  const cycle = maskCycles.find((cycle) => cycle.id === step.mask);
  const visit = visitFor(progress, step.machine, fromMachine);
  const from = animation.index === active ? animation.from : displayed.current;
  const targetMaterial = patternState(active, visit);
  const material = reduced
    ? targetMaterial
    : blendPattern(from.material, targetMaterial, portion(progress, 0, 0.28));
  const camera = patterningCamera(active, progress, from.camera);
  const surfaceHeights = [
    patternSurfaceHeight(material),
    patternSurfaceHeight(material, 0, camera.ymax - 0.001),
  ];
  const machine = machines.find((item) => item.id === visit.machine);
  const machineLabel =
    step.machine === "etch"
      ? step.mask === "gate"
        ? "Polysilicon etch"
        : step.mask === "metal" || step.mask === "upper"
          ? "Metal etch"
          : "Oxide etch"
      : machine?.label;
  const previewMachine = machines.find((item) => item.id === preview);

  const clearPreviewTimers = useCallback(() => {
    clearTimeout(openTimer.current);
    clearTimeout(closeTimer.current);
  }, []);
  const dismissPreview = useCallback(() => {
    clearPreviewTimers();
    pinnedPreview.current = false;
    setPreviewOpen(false);
  }, [clearPreviewTimers]);

  useLayoutEffect(() => {
    displayed.current = {
      material,
      camera: { elevation: camera.elevation, section: camera.section },
    };
  });

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener("change", update);

    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const threshold =
        window.innerWidth < 900
          ? Math.min(
              window.innerHeight * 0.86,
              (stageRef.current?.getBoundingClientRect().bottom ?? 400) + 80,
            )
          : window.innerHeight * 0.52;
      let index = 0;
      sections.current.forEach((element, candidate) => {
        if (element && element.getBoundingClientRect().top <= threshold)
          index = candidate;
      });
      setActive(index);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, []);

  useEffect(() => {
    const origin = displayed.current;
    if (previousScene.current !== active) {
      setFromMachine(scenes[previousScene.current].machine);
      setFromIndex(previousScene.current);
      previousScene.current = active;
    }
    dismissPreview();
    if (reduced) {
      setAnimation({ index: active, progress: 1, from: origin });
      return;
    }

    let frame = 0;
    let elapsed = 0;
    const duration =
      active === 0 || active === stages.inverter
        ? inverterDuration
        : sceneDuration;
    let previous = performance.now();
    const update = (now: number) => {
      frame = 0;
      const rect = stageRef.current?.getBoundingClientRect();
      const visible =
        rect &&
        rect.bottom > 0 &&
        rect.top < window.innerHeight &&
        !document.hidden;
      if (!visible) return;

      elapsed += Math.min(now - previous, 64);
      previous = now;
      setAnimation({
        index: active,
        progress: Math.min(1, elapsed / duration),
        from: origin,
      });
      if (elapsed < duration) frame = requestAnimationFrame(update);
    };
    const resume = () => {
      if (frame || elapsed >= duration || document.hidden) return;

      previous = performance.now();
      frame = requestAnimationFrame(update);
    };
    const observer = new IntersectionObserver(resume);
    if (stageRef.current) observer.observe(stageRef.current);
    document.addEventListener("visibilitychange", resume);
    setAnimation({ index: active, progress: 0, from: origin });
    resume();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      document.removeEventListener("visibilitychange", resume);
    };
  }, [active, reduced, replay, dismissPreview]);

  useEffect(() => clearPreviewTimers, [clearPreviewTimers]);

  useEffect(() => {
    window.addEventListener("scroll", dismissPreview, { passive: true });
    window.addEventListener("resize", dismissPreview);
    window.addEventListener("blur", dismissPreview);

    return () => {
      window.removeEventListener("scroll", dismissPreview);
      window.removeEventListener("resize", dismissPreview);
      window.removeEventListener("blur", dismissPreview);
    };
  }, [dismissPreview]);

  useEffect(() => {
    if (!previewOpen) return;

    const dismissOutside = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Element &&
        roomRef.current?.contains(target) &&
        target.closest(".fab-room-machine, .fab-machine-preview")
      ) {
        return;
      }

      dismissPreview();
    };
    document.addEventListener("pointerdown", dismissOutside);

    return () => document.removeEventListener("pointerdown", dismissOutside);
  }, [previewOpen, dismissPreview]);

  const showPreview = (id: MachineId, immediate = false) => {
    if (pinnedPreview.current && !immediate) return;

    clearPreviewTimers();
    const open = () => {
      setPreview(id);
      setPreviewOpen(true);
    };
    if (immediate) {
      pinnedPreview.current = false;
      open();
    } else {
      openTimer.current = setTimeout(open, 450);
    }
  };
  const keepPreview = () => clearPreviewTimers();
  const togglePreview = (id: MachineId) => {
    if (previewOpen && preview === id && pinnedPreview.current) {
      dismissPreview();
      return;
    }

    clearPreviewTimers();
    pinnedPreview.current = true;
    setPreview(id);
    setPreviewOpen(true);
  };
  const hidePreview = () => {
    clearPreviewTimers();
    if (
      pinnedPreview.current ||
      roomRef.current
        ?.querySelector(".fab-machine-preview")
        ?.contains(document.activeElement)
    ) {
      return;
    }

    closeTimer.current = setTimeout(() => setPreviewOpen(false), 350);
  };
  const closePreview = () => {
    const trigger = roomRef.current?.querySelector<HTMLButtonElement>(
      '.fab-room-info[aria-expanded="true"]',
    );
    dismissPreview();
    trigger?.focus({ preventScroll: true });
  };
  const go = (index: number) => {
    const section = sections.current[index];
    if (!section) return;

    const behaviour = reduced ? "auto" : "smooth";
    if (window.innerWidth < 900) {
      const stageHeight =
        stageRef.current?.getBoundingClientRect().height ?? 450;
      window.scrollTo({
        top:
          window.scrollY +
          section.getBoundingClientRect().top -
          stageHeight -
          88,
        behavior: behaviour,
      });
      return;
    }

    section.scrollIntoView({ behavior: behaviour, block: "center" });
  };

  return (
    <article
      className="fab-article"
      ref={host}
      style={{ "--fab-silicon": siliconColours.top } as CSSProperties}
    >
      <header className="fab-introduction">
        <div className="fab-kicker">
          <span>Sand to Thought</span>
          <span>Deep dive 01</span>
          <span className="fab-draft">First draft</span>
        </div>
        <div dangerouslySetInnerHTML={{ __html: introduction }} />
        <a className="fab-start" href="#fab-destination">
          Follow the wafer <span aria-hidden="true">↓</span>
        </a>
      </header>

      <div className="fab-body">
        <aside
          className="fab-stage"
          data-scene={step.key}
          data-motion={progress < 1 ? "running" : "settled"}
          ref={stageRef}
          aria-label="Fabrication animation"
        >
          <div className="fab-stage-heading">
            <span>
              {String(active + 1).padStart(2, "0")} / {scenes.length}
            </span>
            <span>{step.title}</span>
          </div>
          <div className="fab-lab-heading">
            <span>Clean room</span>
            <span>{machineLabel ?? "Our wafer journey"}</span>
          </div>
          <div
            className="fab-room-host"
            ref={roomRef}
            onFocusCapture={keepPreview}
            onBlurCapture={(event) => {
              if (
                event.relatedTarget &&
                !event.currentTarget.contains(event.relatedTarget)
              ) {
                dismissPreview();
              }
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape" && previewOpen) {
                event.preventDefault();
                event.stopPropagation();
                closePreview();
              }
            }}
          >
            <CleanRoom
              visit={visit}
              preview={previewOpen ? preview : undefined}
              showPreview={showPreview}
              hidePreview={hidePreview}
              togglePreview={togglePreview}
            />
            {previewMachine ? (
              <div
                id="fab-machine-preview"
                className={`fab-machine-preview ${previewOpen ? "is-open" : ""}`}
                role="region"
                aria-labelledby="fab-preview-title"
                aria-hidden={!previewOpen}
                inert={!previewOpen}
                onPointerEnter={keepPreview}
                onPointerLeave={hidePreview}
              >
                <button
                  aria-label="Close machine preview"
                  onClick={closePreview}
                >
                  ×
                </button>
                <span className="fab-preview-source">Wikipedia preview</span>
                <strong id="fab-preview-title">{previewMachine.label}</strong>
                <p id="fab-machine-description">{previewMachine.summary}</p>
                <a
                  href={`https://en.wikipedia.org/wiki/${previewMachine.wiki}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Read on Wikipedia <span aria-hidden="true">↗</span>
                </a>
              </div>
            ) : null}
          </div>
          <div className="fab-observations">
            <figure className="fab-wafer-panel">
              <figcaption>Whole wafer</figcaption>
              <WholeWafer index={active} visit={visit} state={material} />
            </figure>
            <figure className="fab-detail-panel">
              <figcaption>
                One small area <span>Layers enlarged</span>
              </figcaption>
              <PatterningModel
                fromIndex={fromIndex}
                view={camera}
                index={active}
                progress={progress}
                visit={visit}
                state={material}
                input={input}
              />
            </figure>
            {active >= 1 ? (
              <WaferMagnification
                corners={[
                  camera.project([0, 0, surfaceHeights[0]]),
                  camera.project([0, camera.ymax, surfaceHeights[1]]),
                ]}
              />
            ) : null}
          </div>
          <div className="fab-materials" aria-label="Material key">
            {[
              ["silicon", "Silicon"],
              ["oxide", "Insulator"],
              ["resist", "Resist"],
              ["poly", "Gate"],
              ["metal", "Metal"],
            ]
              .filter(
                (_, index) =>
                  active === 0 || active >= stages.poly || index < 3,
              )
              .map(([kind, label]) => (
                <span key={kind}>
                  <i className={`fab-material-${kind}`} />
                  {label}
                </span>
              ))}
          </div>
          <div className="fab-controls">
            <button
              aria-label="Previous fabrication step"
              disabled={active === 0}
              onClick={() => go(active - 1)}
            >
              ←
            </button>
            {inverter ? (
              <div className="fab-input-controls">
                <span>Input A</span>
                {[0, 1].map((value) => (
                  <button
                    key={value}
                    aria-pressed={input === value}
                    onClick={() => {
                      setInput(value);
                      setAnimation({
                        index: active,
                        progress: reduced ? 1 : 0,
                        from: displayed.current,
                      });
                      setReplay((count) => count + 1);
                    }}
                  >
                    {value}
                  </button>
                ))}
                <span>Q = {electrical.output ?? "…"}</span>
              </div>
            ) : (
              <button
                className="fab-replay"
                onClick={() => {
                  setFromMachine(step.machine);
                  setFromIndex(active);
                  setReplay((value) => value + 1);
                }}
              >
                Replay this step <span aria-hidden="true">↻</span>
              </button>
            )}
            <button
              aria-label="Next fabrication step"
              disabled={active === scenes.length - 1}
              onClick={() => go(active + 1)}
            >
              →
            </button>
          </div>
          {cycle ? (
            <div
              className="fab-mask-cycle"
              aria-label={`Mask ${maskCycles.indexOf(cycle) + 1} of ${maskCycles.length}, ${cycle.label}`}
            >
              <span>
                {maskCycles.indexOf(cycle) + 1} / {maskCycles.length} ·{" "}
                {cycle.label}
              </span>
              <ol>
                {(
                  ["coat", "expose", "develop", "operate", "strip"] as const
                ).map((phase) => (
                  <li
                    key={phase}
                    aria-current={step.phase === phase ? "step" : undefined}
                  >
                    {phase === "operate"
                      ? cycle.operation
                      : phase[0].toUpperCase() + phase.slice(1)}
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
          <p className="fab-operation" aria-live="polite">
            {step.operation}
          </p>
        </aside>

        <div className="fab-prose">
          <nav className="fab-contents" aria-label="Article contents">
            {groups.map((group) => (
              <a
                href={`#fab-${group.key}`}
                key={group.key}
                aria-current={
                  step.group === group.group ? "location" : undefined
                }
              >
                {group.group + 1}
              </a>
            ))}
            <span>Read or scroll to build</span>
          </nav>
          {scenes.map((scene, index) => (
            <section
              id={`fab-${scene.key}`}
              className={`fab-step ${active === index ? "is-active" : ""}`}
              data-scene={scene.key}
              key={scene.key}
              ref={(element) => {
                sections.current[index] = element;
              }}
            >
              <span className="fab-step-label">
                {String(index + 1).padStart(2, "0")}{" "}
                <span aria-hidden="true">—</span> {scene.title}
              </span>
              <div dangerouslySetInnerHTML={{ __html: scene.html }} />
            </section>
          ))}
        </div>
      </div>
    </article>
  );
};
