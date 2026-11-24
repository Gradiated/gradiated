import { ArticleOpening } from "../../../shared/ArticleOpening";
import { memo, useRef } from "react";
import { SectionFab } from "../../../../../../product/website/src/components/design";
import { InferenceProfile } from "../../../shared/figures/InferenceProfile";
import { useRailDocNav } from "../../../../../../product/website/src/components/design/RailShell";
import { ChipLayersArtwork } from "../../../../../../product/website/src/components/sand-library/ChipLayersArtwork";
import {
  bibliography,
  chapters,
  closingSceneKeys,
  figureTitles,
  introduction,
  measurementScenes,
  measurementStepFor,
  scenes,
} from "./scenes";
import { useActiveScene } from "./useFpgaJourney";
import { ReconfigureFigure } from "./LogicFigures";
import { ClockTimingFigure } from "./ClockFigures";
import { BoundaryFigure, ResourcesFigure } from "./DeviceFigures";
import { BoardMeasurementTransition } from "./BoardMeasurementTransition";
import { MeasuredProfile } from "./MeasuredProfile";
import { experimentNumbers, MeasurementChart } from "./MeasurementChart";
import { LaterComparison } from "./LaterComparison";
import { laterComparisons, type ComparisonScene } from "./laterComparisons";
import { MeasurementMechanism } from "./MeasurementMechanism";
import { ChipComparisonProfiles } from "./ChipComparisonProfiles";
import "../../../../../../product/website/src/components/sand-library/sand-library.css";
import "./fpga.css";
import { continuationFor } from "./ChipContinuation";
import { applicationFor } from "./ApplicationEnvironments";
import { ContinuationWorld, worldSceneKeys } from "./ContinuationWorld";
import { TransformerFigure } from "./TransformerFigures";
import { OurBoardFigure } from "./LearningFigures";
import { NeuronFigure } from "./NeuronFigure";

const Markup = memo(
  ({ html, className }: { html: string; className?: string }) => (
    <div className={className} dangerouslySetInnerHTML={{ __html: html }} />
  ),
);

const railGroups = [
  {
    items: chapters.map(({ id, label }) => ({ href: `#${id}`, label })),
  },
];

const ActiveFigure = ({
  group,
  scene,
  lecture,
}: {
  group: number;
  scene: string;
  lecture?: boolean;
}) => {
  if ((worldSceneKeys as readonly string[]).includes(scene))
    return (
      <ContinuationWorld
        key={scene === "board-request" ? "our-board" : scene}
        scene={scene}
        lecture={lecture}
      />
    );
  switch (group) {
    case 0:
      return <ReconfigureFigure scene={scene} />;
    case 1:
      return <ClockTimingFigure />;
    case 2:
      return scene === "neuron" || scene === "neuron-next" ? (
        <NeuronFigure key={scene} scene={scene} />
      ) : (
        <ResourcesFigure scene={scene} />
      );
    case 3:
      return scene === "our-board" ? (
        <OurBoardFigure />
      ) : (
        <BoundaryFigure scene={scene} />
      );
    case 4:
      return <TransformerFigure scene={scene} />;
    case 5:
      return <ChipComparisonProfiles />;
    case 6: {
      const later = Object.hasOwn(laterComparisons, scene);
      const step = later
        ? measurementScenes.length + Object.keys(laterComparisons).indexOf(scene)
        : measurementStepFor(scene);
      return (
        <div className="fpga-measurement-stage">
          {later ? <LaterComparison scene={scene as ComparisonScene} /> : <MeasurementMechanism step={step} />}
          <MeasurementChart step={step} />
        </div>
      );
    }
    default:
      throw new Error(`Unknown FPGA figure ${group}`);
  }
};

const kv260LectureSpecifications = [
  {
    label: "Main memory",
    value: (
      <a
        href="https://docs.amd.com/r/en-US/ds987-k26-som/Functional-Overview-and-Block-Diagram"
        target="_blank"
        rel="noopener noreferrer"
      >
        4 GB DDR4 · 19.2 GB/s peak
      </a>
    ),
  },
  {
    label: "FPGA memory",
    value: "648 KiB block RAM + 2.25 MiB UltraRAM",
  },
  {
    label: "Distributed RAM",
    value: "Up to about 450 KiB in writable LUTs",
  },
  {
    label: "Parallel arithmetic",
    value: "1,248 DSP multiply-add units",
  },
  {
    label: "Our model",
    value: "26,720 parameters · about 52 KiB at 16 bits, held in block RAM",
  },
  {
    label: "Fixed weights",
    value: "Can be built into LUTs and wiring",
  },
];

export const FpgaInferenceProfile = ({
  lecture = false,
}: { lecture?: boolean }) => lecture ? (
  <InferenceProfile
    anchor="fpga-inference-profile"
    device="FPGA - AMD Kria KV260"
    illustrativeScores={{
      cost: 0.55,
      throughput: 0.34,
      latency: 0.58,
      capacity: 0.28,
      bandwidth: 0.3,
      energy: 0.6,
    }}
    specifications={kv260LectureSpecifications}
  />
) : <MeasuredProfile />;

export const FpgaFigureStage = ({
  scene,
  zoom,
  showTitle = true,
  lecture,
}: {
  scene: (typeof scenes)[number];
  zoom: "smooth" | "instant";
  showTitle?: boolean;
  lecture?: boolean;
}) => {
  const measurementIntro = !lecture && scene.key === "measuring-inference";
  const boardRequest = !lecture && scene.key === "board-request";
  const chipScene =
    scene.key === "memory-roles" ? "resources-together" : scene.key;
  const continuation = continuationFor(scene.key);
  const chipView =
    scene.group === 0 ||
    Boolean(continuation) ||
    Boolean(applicationFor(scene.key));

  return (
    <aside
      className="fpga-stage"
      tabIndex={0}
      aria-label="FPGA figures"
      data-scene={scene.key}
      data-zoom={zoom}
      data-figure={scene.group}
    >
      {showTitle && !chipView && scene.group < 5 && (
        <h3 className="fpga-figure-title">
          {scene.key === "neuron"
            ? "One neuron, step by step"
            : scene.key === "our-board"
              ? "Where our FPGA fits"
              : scene.key === "transformer-cache"
                ? "Keep earlier keys and values"
                : figureTitles[scene.group]}
        </h3>
      )}
      <BoardMeasurementTransition scene={scene.key} smooth={!lecture && zoom === "smooth"}>
        <div data-board-layer="" hidden={!chipView} aria-hidden={!chipView}>
          <ReconfigureFigure
            scene={measurementIntro ? "board-request" : chipView ? chipScene : "inside-chip"}
            detail={
              measurementIntro || continuation?.detail || continuation?.world ? (
                <ActiveFigure
                  group={scene.group}
                  scene={measurementIntro ? "board-request" : scene.key}
                  lecture={lecture}
                />
              ) : undefined
            }
          />
        </div>
        {(boardRequest || scene.group === 6) && (
          <div data-measurement-layer="" hidden={boardRequest} aria-hidden={boardRequest}>
            <ActiveFigure group={6} scene={boardRequest ? "measuring-inference" : scene.key} />
          </div>
        )}
        {!chipView && scene.group !== 6 && <ActiveFigure group={scene.group} scene={scene.key} />}
      </BoardMeasurementTransition>
    </aside>
  );
};

const finalProfile = scenes.find((scene) => scene.key === "final-profile")!;
const finalProfileNotes = scenes.find((scene) => scene.key === "final-profile-notes")!;
const chipComparison = scenes.find((scene) => scene.key === "chip-choices")!;
const outlookTrends = scenes.find((scene) => scene.key === "outlook-trends")!;
const scrollScenes = scenes.filter(
  (scene) => !closingSceneKeys.some((key) => key === scene.key),
);

export const FpgaJourney = ({ author }: { author: string }) => {
  const host = useRef<HTMLElement>(null);
  const { active, zoom } = useActiveScene(host, scrollScenes.length);
  const scene = scrollScenes[active];
  const chapter = chapters
    .filter((candidate) => candidate.index <= active)
    .at(-1);
  useRailDocNav({
    author,
    title: "Sand to Thought",
    current: chapter ? `#${chapter.id}` : "",
    groups: railGroups,
    backHref: "/library/",
  });

  return (
    <article className="fpga-article" ref={host}>
      <div className="fpga-layout">
        <SectionFab label="Article contents">
          {chapters.map(({ id, label }) => (
            <a
              key={id}
              className="gr-fab-link"
              href={`#${id}`}
              aria-current={id === chapter?.id ? "location" : undefined}
            >
              {label}
            </a>
          ))}
        </SectionFab>
        <div className="fpga-main">
          <a
            className="fpga-cover"
            href="#fpga-reconfigure"
            aria-label="Begin the FPGA guide"
          >
            <ChipLayersArtwork variant="fpga" />
          </a>
          <ArticleOpening author={author}>
            <header className="fpga-introduction">
              <Markup html={introduction} />
            </header>
          </ArticleOpening>
          <FpgaInferenceProfile />
          <div className="fpga-body fpga-columns">
            <FpgaFigureStage scene={scene} zoom={zoom} />
            <div className="fpga-prose">
              {scrollScenes.map((item, index) => (
                <section
                  key={item.key}
                  id={`fpga-${item.key}`}
                  className={`fpga-scene ${index === active ? "is-active" : ""}`}
                  data-fpga-scene={index}
                >
                  <Markup html={item.html} />
                </section>
              ))}
            </div>
          </div>
          <MeasuredProfile
            summary={
              <Markup className="kv-profile-summary" html={finalProfile.html} />
            }
            readingGuide={<Markup html={finalProfileNotes.html} />}
          />
          <section className="kv-chip-section" id="fpga-chip-choices" aria-label="Comparing inference chips">
            <Markup className="kv-chip-text" html={chipComparison.html} />
            <ChipComparisonProfiles compact />
          </section>
          <section className="fpga-outlook-trends fpga-columns" id="fpga-outlook-trends" aria-label="Outlook and inference experiment trends">
            <Markup className="kv-chip-text" html={outlookTrends.html} />
            <div className="fpga-measurement-stage">
              <MeasurementChart step={experimentNumbers.length - 1} overview />
            </div>
          </section>
          <Markup className="fpga-bibliography" html={bibliography} />
        </div>
      </div>
    </article>
  );
};
