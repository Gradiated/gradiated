import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { FabricationJourney } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/FabricationJourney";
import { inverterDuration } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/process";

const playback = vi.hoisted(() => ({
  effects: [] as (() => void | (() => void))[],
  refs: [] as { current: unknown }[],
  writes: [] as unknown[],
}));

vi.mock("react", async (importOriginal) => {
  const react = await importOriginal<typeof import("react")>();

  return {
    ...react,
    useEffect: (effect: () => void | (() => void)) =>
      playback.effects.push(effect),
    useLayoutEffect: () => {},
    useRef: (current: unknown) => {
      const ref = { current };
      playback.refs.push(ref);
      return ref;
    },
    useState: (initial: unknown) => {
      let value = initial;
      return [
        value,
        (next: unknown) => {
          value = typeof next === "function" ? next(value) : next;
          playback.writes.push(value);
        },
      ];
    },
  };
});
vi.mock("../src/components/design", () => ({ SectionFab: () => null }));
vi.mock("../src/components/sand-library/ChipLayersArtwork", () => ({
  ChipLayersArtwork: () => null,
}));
vi.mock(
  "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/FabricationLab",
  () => ({
    CleanRoom: () => null,
    WholeWafer: () => null,
  }),
);
vi.mock(
  "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/PatterningModel",
  async (load) => ({
    ...(await load<object>()),
    PatterningModel: () => null,
  }),
);
vi.mock(
  "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/FabricationIntroduction",
  async (load) => ({
    ...(await load<object>()),
    useOpeningLayout: () => undefined,
  }),
);
vi.mock(
  "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/WaferMagnification",
  () => ({
    WaferMagnification: () => null,
  }),
);
vi.mock(
  "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/InterconnectStack",
  () => ({
    InterconnectStack: () => null,
  }),
);

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const startPlayback = () => {
  playback.effects = [];
  playback.refs = [];
  playback.writes = [];
  renderToStaticMarkup(createElement(FabricationJourney));
  for (const ref of playback.refs) {
    if (ref.current === null) {
      ref.current = {
        getBoundingClientRect: () => ({ top: 100, bottom: 500 }),
      };
    }
  }

  let now = 0;
  let frameId = 0;
  const frames = new Map<number, FrameRequestCallback>();
  const listeners = new Map<string, () => void>();
  const addEventListener = (name: string, callback: () => void) =>
    listeners.set(name, callback);
  const removeEventListener = (name: string, callback: () => void) => {
    if (listeners.get(name) === callback) listeners.delete(name);
  };
  const document = { hidden: false, addEventListener, removeEventListener };
  vi.spyOn(performance, "now").mockImplementation(() => now);
  vi.stubGlobal("window", {
    innerWidth: 1200,
    innerHeight: 800,
    addEventListener,
    removeEventListener,
    matchMedia: () => ({
      matches: false,
      addEventListener,
      removeEventListener,
    }),
  });
  vi.stubGlobal("document", document);
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.set(++frameId, callback);
    return frameId;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  const cleanups = playback.effects.map((effect) => effect());

  return {
    document,
    frames,
    listeners,
    tick: (time: number) => {
      now = time;
      for (const [id, callback] of [...frames]) {
        frames.delete(id);
        callback(now);
      }
    },
    setTime: (time: number) => {
      now = time;
    },
    stop: () => cleanups.toReversed().forEach((cleanup) => cleanup?.()),
  };
};
const animationWrites = () =>
  playback.writes.filter(
    (value): value is { progress: number; transition: number } =>
      typeof value === "object" && value !== null && "progress" in value,
  );

it("holds the finished opening without React updates, then starts the opposite input", () => {
  const clock = startPlayback();
  clock.tick(inverterDuration);
  expect(animationWrites().at(-1)).toMatchObject({
    progress: 1,
    transition: 1,
  });
  const settledWrites = animationWrites().length;
  clock.tick(inverterDuration + 500);
  clock.tick(inverterDuration + 1700);
  expect(animationWrites()).toHaveLength(settledWrites);

  clock.tick(inverterDuration + 1800);
  expect(animationWrites()).toHaveLength(settledWrites + 1);
  expect(animationWrites().at(-1)).toMatchObject({
    progress: 0,
    transition: 1,
  });
  expect(playback.writes).toContain(1);
  clock.stop();
  expect(clock.frames.size).toBe(0);
});

it("pauses a hidden tab and resumes its remaining hold without skipping a cycle", () => {
  const clock = startPlayback();
  clock.tick(inverterDuration);
  const settledWrites = animationWrites().length;
  clock.document.hidden = true;
  clock.tick(inverterDuration + 600);
  expect(clock.frames.size).toBe(0);

  clock.setTime(inverterDuration + 10_000);
  clock.document.hidden = false;
  clock.listeners.get("visibilitychange")?.();
  clock.tick(inverterDuration + 10_100);
  expect(animationWrites()).toHaveLength(settledWrites);
  clock.tick(inverterDuration + 11_800);
  expect(animationWrites().at(-1)).toMatchObject({ progress: 0 });
  clock.stop();
  expect(clock.frames.size).toBe(0);
});

it("shows the lecture title, chapter navigation and controls without article prose", () => {
  const lecture = renderToStaticMarkup(
    createElement(FabricationJourney, { lecture: true }),
  );
  const article = renderToStaticMarkup(createElement(FabricationJourney));

  expect(lecture).toContain("Lecture 3");
  expect(lecture).toContain('aria-label="Lecture contents"');
  expect(lecture).toContain('aria-label="Next step"');
  expect(lecture).toContain('aria-label="Replay animation"');
  expect(lecture).toContain('class="fab-cover"');
  expect(lecture).not.toContain('class="fab-prose"');
  expect(lecture).not.toContain('class="fab-bibliography"');
  expect(article).toContain('class="fab-prose"');
  expect(article).not.toContain('class="fab-side gr-doc-side"');
  expect(article).not.toContain('aria-label="Next step"');
});
