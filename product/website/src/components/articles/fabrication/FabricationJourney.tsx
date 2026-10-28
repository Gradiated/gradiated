import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import type { CSSProperties } from "react";
import { SectionFab } from "../../design";
import { ChipLayersArtwork } from "../../sand-library/ChipLayersArtwork";
import { siliconColours } from "./materials";
import { CleanRoom, WholeWafer } from "./FabricationLab";
import { PatterningModel, patterningCamera } from "./PatterningModel";
import { InverterViews } from "./InverterViews";
import { InterconnectStack } from "./InterconnectStack";
import {
  initialOpening,
  openingState,
  useOpeningLayout,
  WaferTransfer,
} from "./FabricationIntroduction";
import type { OpeningState } from "./FabricationIntroduction";
import { WaferMagnification } from "./WaferMagnification";
import {
  transitionPattern,
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
import { bibliography, introduction, machines, scenes } from "./model";
import type { MachineId } from "./model";
import "../../sand-library/sand-library.css";
import "./fabrication.css";

// Keep native disclosures and citation targets intact during animation updates.
const FabricationMarkup = memo(
  ({ html, className }: { html: string; className?: string }) => (
    <div className={className} dangerouslySetInnerHTML={{ __html: html }} />
  ),
);

const articleLabels = (
  <div className="fab-kicker">
    <span>Sand to Thought</span>
    <span>Deep dive</span>
    <span className="fab-topic">Fabrication</span>
  </div>
);

const chapters = scenes.flatMap((scene, index) => {
  const heading = scene.html.match(/<h2[^>]*>(.*?)<\/h2>/s);

  return heading ? [{ id: `fab-${scene.key}`, label: heading[1], index }] : [];
});

type Presentation = {
  material: PatternState;
  camera: CameraState;
  opening: OpeningState;
  workingInverter: number;
  wiringOverview: number;
};
const initialPresentation: Presentation = {
  material: patternState(0, visitFor(1, undefined, undefined)),
  camera: { elevation: 0.62, section: 0 },
  opening: initialOpening,
  workingInverter: 0,
  wiringOverview: 0,
};

export const FabricationJourney = () => {
  const host = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLElement>(null);
  const roomRef = useRef<HTMLDivElement>(null);
  const visualsRef = useRef<HTMLDivElement>(null);
  const openingLayout = useOpeningLayout(visualsRef);
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
    transition: 1,
    from: initialPresentation,
  });
  const displayed = useRef<Presentation>(initialPresentation);
  const previousScene = useRef(0);
  const [fromMachine, setFromMachine] = useState<MachineId>();
  const [fromIndex, setFromIndex] = useState(1);
  const [input, setInput] = useState(0);
  const [openingAuto, setOpeningAuto] = useState(true);
  const [preview, setPreview] = useState<MachineId | undefined>();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [replay, setReplay] = useState(0);
  const progress = reduced
    ? 1
    : animation.index === active
      ? animation.progress
      : 0;
  const transition = reduced
    ? 1
    : animation.index === active
      ? animation.transition
      : 0;
  const inverter = active === 0 || active === stages.inverter;
  const electrical = inverterOperation(input, progress);
  const step = scenes[active];
  const activeChapter = chapters
    .filter((chapter) => chapter.index <= active)
    .pop();
  const visit = visitFor(progress, step.machine, fromMachine);
  const from = animation.index === active ? animation.from : displayed.current;
  const sourceIndex =
    animation.index === active ? fromIndex : previousScene.current;
  const skippedScenes = Math.abs(active - sourceIndex) > 1;
  const materialReveal =
    reduced || !skippedScenes ? 1 : portion(transition, 0, 0.28);
  const workingInverter =
    from.workingInverter +
    ((active === stages.inverter ? 1 : 0) - from.workingInverter) *
      portion(transition, 0, 0.24);
  const wiringOverview =
    from.wiringOverview +
    ((step.key === "finish" ? 1 : 0) - from.wiringOverview) *
      portion(transition, 0, step.key === "finish" ? 0.08 : 0.24);
  const targetMaterial = patternState(active, visit);
  const material = reduced
    ? targetMaterial
    : transitionPattern(
        from.material,
        targetMaterial,
        portion(transition, 0, 0.28),
        sourceIndex,
        active,
      );
  const camera = patterningCamera(active, transition, from.camera);
  const opening = openingState(active, transition, from.opening);
  const entering = active === stages.operator && from.opening.entry < 0.99;
  const detailReveal = portion(opening.magnify, 0.3, 1);
  const door =
    entering && !reduced
      ? portion(progress, 0, 0.12) * (1 - portion(progress, 0.86, 1))
      : 0;
  const doorOpen =
    entering && !reduced
      ? portion(progress, 0.08, 0.25) * (1 - portion(progress, 0.7, 0.86))
      : 0;
  const surfaceHeights = [
    patternSurfaceHeight(material),
    patternSurfaceHeight(material, 0, camera.ymax - 0.001),
  ];
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
      opening,
      workingInverter,
      wiringOverview,
      camera: {
        elevation: camera.elevation,
        section: camera.section,
        scale: camera.scale,
        centreY: camera.centreY,
        cutY: camera.cutY,
      },
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
    const skippedScenes = Math.abs(active - previousScene.current) > 1;
    if (previousScene.current !== active) {
      setFromMachine(scenes[previousScene.current].machine);
      setFromIndex(previousScene.current);
      previousScene.current = active;
    }
    dismissPreview();
    if (reduced) {
      setAnimation({ index: active, progress: 1, transition: 1, from: origin });
      return;
    }

    let frame = 0;
    let elapsed = 0;
    let transitionElapsed = 0;
    const duration =
      active === 0 || active === stages.inverter
        ? inverterDuration
        : active <= stages.layout
          ? active === stages.operator
            ? 2200
            : 1600
          : sceneDuration;
    const transitionDuration = skippedScenes
      ? Math.min(duration, 1200)
      : duration;
    const looping = active === 0 && openingAuto;
    const cycleDuration = inverterDuration + 1800;
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

      const delta = now - previous;
      elapsed += delta;
      transitionElapsed += delta;
      previous = now;
      if (looping && elapsed >= cycleDuration) {
        elapsed = 0;
        setInput((value) => 1 - value);
      }
      setAnimation({
        index: active,
        progress: Math.min(1, elapsed / duration),
        transition: Math.min(1, transitionElapsed / transitionDuration),
        from: origin,
      });
      if (looping || elapsed < duration) frame = requestAnimationFrame(update);
    };
    const resume = () => {
      if (frame || (!looping && elapsed >= duration) || document.hidden) return;

      previous = performance.now();
      frame = requestAnimationFrame(update);
    };
    const observer = new IntersectionObserver(resume);
    if (stageRef.current) observer.observe(stageRef.current);
    document.addEventListener("visibilitychange", resume);
    setAnimation({ index: active, progress: 0, transition: 0, from: origin });
    resume();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      document.removeEventListener("visibilitychange", resume);
    };
  }, [active, reduced, replay, openingAuto, dismissPreview]);

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

  const physicalView = (
    <PatterningModel
      fromIndex={fromIndex}
      view={camera}
      index={active}
      progress={progress}
      visit={visit}
      state={material}
      input={input}
    />
  );

  return (
    <article
      className="fab-article"
      ref={host}
      style={{ "--fab-silicon": siliconColours.top } as CSSProperties}
    >
      <div className="fab-layout">
        <aside className="fab-side gr-doc-side">
          {articleLabels}
          <nav aria-label="Article contents" className="gr-doc-nav">
            <div className="gr-doc-nav-group">
              {chapters.map((chapter) => (
                <a
                  className="gr-doc-nav-link"
                  href={`#${chapter.id}`}
                  key={chapter.id}
                  aria-current={
                    activeChapter?.id === chapter.id ? "location" : undefined
                  }
                >
                  {chapter.label}
                </a>
              ))}
            </div>
          </nav>
        </aside>
        <SectionFab label="Article contents">
          <div className="fab-menu-labels">{articleLabels}</div>
          {chapters.map((chapter) => (
            <a
              className="gr-fab-link fab-guide-link"
              href={`#${chapter.id}`}
              key={chapter.id}
              aria-current={
                activeChapter?.id === chapter.id ? "location" : undefined
              }
            >
              {chapter.label}
            </a>
          ))}
        </SectionFab>
        <div className="fab-main">
          <a
            className="fab-cover"
            href="#fab-introduction"
            aria-label="Begin How do we print a transistor onto silicon?"
          >
            <ChipLayersArtwork />
          </a>
          <header className="fab-introduction" id="fab-introduction">
            <FabricationMarkup html={introduction} />
          </header>

          <div className="fab-body">
            <aside
              className="fab-stage"
              data-scene={step.key}
              data-motion={progress < 1 ? "running" : "settled"}
              ref={stageRef}
              aria-label="Fabrication animation"
            >
              <div className="fab-visuals" ref={visualsRef}>
                <div
                  className="fab-lab-heading"
                  style={{ opacity: opening.room }}
                >
                  Gradiated’s backyard clean room
                </div>
                <div
                  className="fab-room-host"
                  style={{ opacity: opening.room }}
                  aria-hidden={opening.room < 0.01}
                  inert={opening.room < 0.99}
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
                    state={material}
                    machinesOpacity={opening.machines}
                    operatorOpacity={opening.operator}
                    entry={opening.entry}
                    held={portion(opening.transfer, 0.94, 1)}
                    door={door}
                    doorOpen={doorOpen}
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
                      <span className="fab-preview-source">
                        Wikipedia preview
                      </span>
                      <strong id="fab-preview-title">
                        {previewMachine.label}
                      </strong>
                      <p id="fab-machine-description">
                        {previewMachine.summary}
                      </p>
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
                  <figure className="fab-wafer-panel" aria-label="Whole wafer">
                    <div
                      className="fab-wafer-position"
                      style={{
                        opacity: opening.wafer * materialReveal,
                        transform: openingLayout
                          ? `translate(${openingLayout.dx * opening.centred}px, ${openingLayout.dy * opening.centred}px) scale(${1 + (openingLayout.scale - 1) * opening.centred})`
                          : undefined,
                      }}
                      aria-hidden={opening.wafer < 0.01}
                    >
                      <WholeWafer
                        index={active}
                        visit={visit}
                        state={material}
                        gloves={opening.gloves}
                        detail={portion(opening.magnify, 0, 0.3)}
                      />
                    </div>
                  </figure>
                  <figure
                    className="fab-detail-panel"
                    style={{ opacity: detailReveal * materialReveal }}
                    aria-hidden={detailReveal < 0.01}
                    inert={detailReveal < 0.99}
                    aria-label="Enlarged wafer region"
                  >
                    {opening.magnify > 0 ? physicalView : null}
                  </figure>
                  {opening.magnify > 0 ? (
                    <WaferMagnification
                      opacity={portion(opening.magnify, 0.15, 0.35)}
                      progress={portion(opening.magnify, 0.15, 1)}
                      corners={[
                        camera.project([0, 0, surfaceHeights[0]]),
                        camera.project([0, camera.ymax, surfaceHeights[1]]),
                      ]}
                    />
                  ) : null}
                </div>
                <WaferTransfer
                  layout={openingLayout}
                  progress={opening.transfer}
                  state={material}
                />
                {Math.max(opening.destination, workingInverter) > 0 ? (
                  <div
                    className="fab-opening-destination"
                    style={{
                      opacity: Math.max(opening.destination, workingInverter),
                    }}
                    inert={!inverter}
                    aria-hidden={!inverter}
                  >
                    <InverterViews
                      input={input}
                      progress={inverter ? progress : 1}
                    >
                      <PatterningModel
                        fromIndex={0}
                        view={patterningCamera(
                          0,
                          1,
                          initialPresentation.camera,
                        )}
                        index={0}
                        progress={inverter ? progress : 1}
                        visit={visitFor(1, undefined, undefined)}
                        state={initialPresentation.material}
                        input={input}
                      />
                    </InverterViews>
                  </div>
                ) : null}
                {wiringOverview > 0 ? (
                  <div
                    className="fab-wiring-overview"
                    style={{ opacity: wiringOverview }}
                    aria-hidden={step.key !== "finish"}
                  >
                    <InterconnectStack
                      progress={step.key === "finish" ? progress : 1}
                      state={material}
                      camera={camera}
                    />
                  </div>
                ) : null}
              </div>
              {inverter ? (
                <div className="fab-controls">
                  <div className="fab-input-controls">
                    <span>Input</span>
                    {[0, 1].map((value) => (
                      <button
                        key={value}
                        aria-pressed={input === value}
                        onClick={() => {
                          setInput(value);
                          setOpeningAuto(false);
                          setAnimation({
                            index: active,
                            progress: reduced ? 1 : 0,
                            transition: 1,
                            from: displayed.current,
                          });
                          setReplay((count) => count + 1);
                        }}
                      >
                        {value}
                      </button>
                    ))}
                    <span>Output = {electrical.output ?? "…"}</span>
                  </div>
                </div>
              ) : null}
            </aside>

            <div className="fab-prose">
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
                  <FabricationMarkup html={scene.html} />
                </section>
              ))}
            </div>
          </div>
          {bibliography ? (
            <FabricationMarkup
              className="fab-bibliography"
              html={bibliography}
            />
          ) : null}
        </div>
      </div>
    </article>
  );
};
