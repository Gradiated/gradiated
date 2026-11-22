import { StrictMode, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "../../../../../product/website/src/legacy.css";
import "../../../../../product/website/src/tailwind.css";
import "../../../../../product/website/src/styles/index.css";
import {
  FpgaFigureStage,
  FpgaInferenceProfile,
} from "../../articles/fpga/figures/FpgaJourney";
import { ProfilePlot } from "../../articles/fpga/figures/MeasuredProfile";
import { ChipComparisonProfiles } from "../../articles/fpga/figures/ChipComparisonProfiles";
import { chapters, scenes } from "../../articles/fpga/figures/scenes";
import { ChipLayersArtwork } from "../../../../../product/website/src/components/sand-library/ChipLayersArtwork";
import {
  ChipChoicesSlide,
  InferenceComparisonSlide,
  InferenceExperimentSlide,
} from "./Closing";
import "./presentation.css";
import { ExperimentSlide } from "./ExperimentSlide";
import { stories } from "./experimentStories";

const sceneTitles = {
  reconfigure: "A chip that can change its job",
  "map-io": "Pins connect to the outside world",
  "map-logic": "Configurable logic blocks",
  "map-routing": "Wires between blocks",
  "map-junctions": "Switches choose the connections",
  "first-circuit": "Our first circuit",
  "input-change": "Change an input",
  "why-fpgas": "Filter particle collisions",
  "why-display": "Drive a wall of LEDs",
  "why-prototype": "Prototype a custom chip",
  "inside-chip": "Zoom into a logic block",
  "clb-resources": "What fits inside a logic block?",
  "inside-clb": "One look-up table and one flip-flop",
  "truth-table": "Four possible input combinations",
  selector: "Follow a bit through the selectors",
  "stored-bit": "How SRAM holds one answer",
  "write-and-hold": "Write a new answer",
  "cell-hold": "Keep the new answer",
  lut: "Turn AND into OR",
  "flip-flop": "A result is waiting",
  "logic-block": "Capture the result on a clock edge",
  "flip-flop-hold": "Hold the last result",
  "clb-output-setting": "Choose the direct or saved result",
  "routing-grid": "Join two logic blocks",
  "routing-switch": "Open a routing switch",
  "routing-change": "Select a different wire",
  "routing-input": "Send new data down the same wire",
  "configuration-map": "From one setting to a whole chip",
  "configuration-source": "Load a bitstream",
  "configuration-distribute": "Send a setting to the routing",
  "configuration-luts": "Load the LUT answers",
  "clock-network": "Distribute the clock",
  "resources-map": "Make room for working data",
  "block-ram": "Read and write block RAM",
  "arithmetic-map": "Find the arithmetic blocks",
  "arithmetic-blocks": "Multiply two numbers",
  "arithmetic-accumulate": "Prepare a running total",
  "arithmetic-save": "Save the running total",
  "arithmetic-next": "Add the next product",
  pins: "Follow a calculation across the chip",
  "memory-roles": "Memory has several jobs",
  "resource-columns": "A chip full of specialised blocks",
  "neuron-map": "Our extremely overfitted transformer",
  "network-sum": "Zoom into a weighted sum",
  "network-products": "Two products, one sum",
  "neuron-hardware": "Map the sum onto hardware",
  neuron: "Save the first product",
  "neuron-next": "Add the second product",
  "transformer-cache-map": "Now where does KV cache go?",
  "transformer-cache": "Save the keys and values",
  "token-journey": "From a to R to Re",
  "our-board": "What is on the KV260?",
  "board-request": "Follow a request through the board",
};

type Slide = {
  id: string;
  title: string;
  chapter: string;
} & (
  | { kind: "cover" | "profile" | "chip-choices" | "comparison" | "experiments" | "final-profile" | "chip-profiles" }
  | { kind: "scene"; scene: (typeof scenes)[number] }
);

const slides: Slide[] = [
  {
    id: "cover",
    title: "Inside our FPGA",
    chapter: "cover",
    kind: "cover",
  },
  {
    id: "fpga-inference-profile",
    title: "How would we compare this chip?",
    chapter: "cover",
    kind: "profile",
  },
  ...Object.entries(sceneTitles).map<Slide>(([key, title]) => {
    // The lecture retains the input-change animation in the same chapter as routing-change.
    const articleKey = key === "routing-input" ? "routing-change" : key;
    const index = scenes.findIndex((scene) => scene.key === articleKey);
    const articleScene = scenes[index];
    const scene = articleScene && { ...articleScene, key };
    if (!scene) throw new Error(`Missing FPGA lecture scene: ${key}`);

    const chapter =
      chapters.filter((item) => item.index <= index).at(-1)?.id ?? "cover";
    return { id: `fpga-${key}`, title, chapter, kind: "scene", scene };
  }),
  {
    id: "fpga-chip-choices",
    title: "Choose the chip for the job",
    chapter: "fpga-chip-choices",
    kind: "chip-choices",
  },
  {
    id: "fpga-measuring-inference",
    title: "Experiments with inference on our FPGA",
    chapter: "fpga-measuring-inference",
    kind: "comparison",
  },
  {
    id: "fpga-throughput-example",
    title: "How far can we push this FPGA?",
    chapter: "fpga-measuring-inference",
    kind: "experiments",
  },
  ...scenes
    .filter(({ key }) => key === "measuring-inference" || key.startsWith("measure-"))
    .map<Slide>((scene) => {
      const baseline = scene.key === "measuring-inference";
      const title = baseline ? "Baseline: the CPU chooses the next token" :
        new DOMParser().parseFromString(scene.html, "text/html").querySelector("h3")?.textContent;
      if (!title) throw new Error(`Missing experiment heading for ${scene.key}`);
      return {
        id: baseline ? "fpga-measured-baseline" : `fpga-${scene.key}`,
        title,
        chapter: "fpga-measured-baseline",
        kind: "scene",
        scene,
      };
    }),
  {
    id: "fpga-final-profile",
    title: "The same FPGA, after 24 experiments",
    chapter: "fpga-final-profile",
    kind: "final-profile",
  },
  {
    id: "fpga-chip-profiles",
    title: "How would other chips run the same model?",
    chapter: "fpga-final-profile",
    kind: "chip-profiles",
  },
];

const chapterLinks = [
  { id: "cover", label: "Cover and introduction" },
  ...chapters,
  { id: "fpga-chip-choices", label: "Choosing a chip" },
  { id: "fpga-measured-baseline", label: "Measured experiments" },
  { id: "fpga-final-profile", label: "Results and chip comparison" },
]
  .flatMap(({ id, label }) => {
    const index = slides.findIndex((slide) => slide.chapter === id);

    return index < 0 ? [] : [{ id, label, index }];
  })
  .sort((a, b) => a.index - b.index);

const slideFromHash = () => {
  const index = slides.findIndex(({ id }) => window.location.hash === `#${id}`);

  return Math.max(0, index);
};

const Lecture4 = () => {
  const [position, setPosition] = useState<{
    index: number;
    zoom: "smooth" | "instant";
  }>(() => ({ index: slideFromHash(), zoom: "instant" }));
  const [replay, setReplay] = useState(0);
  const { index, zoom } = position;
  const slide = slides[index];

  const navigate = useCallback(
    (next: number, smooth = false) => {
      if (next < 0 || next >= slides.length || next === index) return;

      window.history.replaceState(null, "", `#${slides[next].id}`);
      setReplay(0);
      setPosition({ index: next, zoom: smooth ? "smooth" : "instant" });
    },
    [index],
  );

  useEffect(() => {
    const onHashChange = () => {
      setReplay(0);
      setPosition({ index: slideFromHash(), zoom: "instant" });
    };

    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (
        event.defaultPrevented ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        (event.target instanceof Element &&
          event.target.closest("input, textarea, select, [contenteditable]"))
      )
        return;

      const direction =
        event.key === "ArrowRight" || event.key === "PageDown"
          ? 1
          : event.key === "ArrowLeft" || event.key === "PageUp"
            ? -1
            : 0;
      if (!direction) return;

      event.preventDefault();
      navigate(index + direction, true);
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, navigate]);

  return (
    <main className="fpga-article fpga-lecture">
      <div className="fpga-lecture-layout">
        <nav
          className="gr-doc-nav fpga-lecture-contents"
          aria-label="Lecture contents"
        >
          {chapterLinks.map((chapter) => (
            <a
              className="gr-doc-nav-link"
              key={chapter.id}
              href={`#${slides[chapter.index].id}`}
              aria-current={
                slide.chapter === chapter.id ? "location" : undefined
              }
              onClick={(event) => {
                if (
                  event.metaKey ||
                  event.ctrlKey ||
                  event.shiftKey ||
                  event.altKey
                )
                  return;

                event.preventDefault();
                navigate(chapter.index);
              }}
            >
              {chapter.label}
            </a>
          ))}
        </nav>
        <section
          className="fpga-lecture-slide"
          aria-labelledby="lecture-slide-title"
        >
          <header className="fpga-lecture-heading">
            <select
              aria-label="Lecture contents"
              className="fpga-lecture-chapters"
              value={slide.chapter}
              onChange={(event) => {
                const chapter = chapterLinks.find(
                  ({ id }) => id === event.target.value,
                );
                if (chapter) navigate(chapter.index);
              }}
            >
              {chapterLinks.map(({ id, label }) => (
                <option value={id} key={id}>
                  {label}
                </option>
              ))}
            </select>
            {slide.kind === "cover" && <p>Lecture 4</p>}
            <h1 id="lecture-slide-title">{slide.title}</h1>
            {slide.kind === "cover" && <p>A chip you can reconfigure.</p>}
          </header>

          <div className="fpga-lecture-visual" key={replay}>
            {slide.kind === "scene" && (Object.hasOwn(stories, slide.scene.key) ? (
              <ExperimentSlide scene={slide.scene.key} />
            ) : (
              <FpgaFigureStage
                scene={slide.scene}
                zoom={zoom}
                showTitle={false}
                lecture
              />
            ))}
            {slide.kind === "cover" && (
              <button
                className="fpga-cover fpga-lecture-cover"
                type="button"
                aria-label="Begin Lecture 4"
                data-grain-trigger
                onClick={() => navigate(1)}
              >
                <ChipLayersArtwork
                  variant="fpga"
                  morphSpeed={2.5}
                  playOnMount={replay > 0}
                />
              </button>
            )}
            {slide.kind === "profile" && (
              <div className="fpga-lecture-closing fpga-lecture-inference-profile">
                <FpgaInferenceProfile lecture />
              </div>
            )}
            {slide.kind === "final-profile" && (
              <div className="fpga-lecture-closing">
                <figure className="kv-profile lecture-result-profile">
                  <ProfilePlot comparison title="KV260 baseline and experiment 24" />
                  <figcaption>
                    <div className="kv-profile-key">
                      <span>Baseline experiment · 50 MHz</span>
                      <span>Experiment 24 · 52.63 MHz</span>
                    </div>
                    <p>The same model went from 205 to 1,222 tokens per second. Most of the gain came at 50 MHz as we cut waiting and did more work on each tick.</p>
                    <p>Each joule supplied to the module produced about six times as many output tokens. The board still had the same memory.</p>
                  </figcaption>
                </figure>
              </div>
            )}
            {slide.kind === "chip-profiles" && (
              <div className="fpga-lecture-closing lecture-chip-profiles">
                <ChipComparisonProfiles />
              </div>
            )}
            {slide.kind === "chip-choices" && <ChipChoicesSlide />}
            {slide.kind === "comparison" && <InferenceComparisonSlide />}
            {slide.kind === "experiments" && <InferenceExperimentSlide />}
          </div>

          <div
            className="fpga-lecture-navigation"
            aria-label="Slide controls"
            role="group"
          >
            <button
              type="button"
              onClick={() => navigate(index - 1, true)}
              disabled={index === 0}
              aria-label="Previous slide"
            >
              ←
            </button>
            <span aria-live="polite" aria-atomic="true">
              {index + 1} / {slides.length}
            </span>
            <button
              type="button"
              onClick={() => navigate(index + 1, true)}
              disabled={index === slides.length - 1}
              aria-label="Next slide"
            >
              →
            </button>
            <button
              type="button"
              onClick={() => navigate(0)}
              disabled={index === 0}
            >
              Back to start
            </button>
            <button
              type="button"
              disabled={slide.kind !== "scene" && slide.kind !== "cover"}
              onClick={() => setReplay((value) => value + 1)}
            >
              Replay
            </button>
          </div>
        </section>
      </div>
    </main>
  );
};

const root = document.getElementById("root");
if (!root) throw new Error("The lecture root element is missing.");

const app = createRoot(root);
app.render(
  <StrictMode>
    <div className="gr-root">
      <Lecture4 />
    </div>
  </StrictMode>,
);

if (import.meta.hot) import.meta.hot.dispose(() => app.unmount());
