import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import {
  CloseupProcessEffects,
  WaferProcessEffects,
} from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/ProcessEffects";
import {
  patternState,
  patternSurfaceHeight,
  siliconSurfaceHeight,
  stages,
} from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/process";
import type { Visit } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/process";
import { steps } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/sequence";

const render = (index: number, process: number) => {
  const visit: Visit = {
    machine: steps[index].machine,
    process,
    progress: 0.6,
    loaded: 1,
    working: true,
  };
  const state = patternState(index, visit);
  const markup = renderToStaticMarkup(
    createElement(CloseupProcessEffects, {
      index,
      visit,
      state,
      ymax: 34,
      project: ([x, , z]) => [x, z],
    }),
  );

  return { markup, state, visit };
};

const implantParticles = (markup: string) =>
  [...markup.matchAll(/<circle\b[^>]*data-implant-site="[^"]+"[^>]*>/g)].map(
    ([tag]) =>
      Object.fromEntries(
        [...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map(([, key, value]) => [
          key,
          value,
        ]),
      ),
  );

it.each([stages.well, stages.implant, stages.implantP])(
  "uses an equally spaced incoming beam with the same particle size and brightness above every material, scene %i",
  (index) => {
    const { markup, state } = render(index, 0.4);
    const particles = implantParticles(markup);
    expect(particles).toHaveLength(52);
    const rows = new Map<number, number[]>();
    const beamTop =
      Math.max(
        ...particles.map((particle) => {
          const [x, y] = particle["data-implant-site"].split(" ").map(Number);
          return patternSurfaceHeight(state, x, y);
        }),
      ) + 12;
    let incoming = 0;
    for (const particle of particles) {
      const [x, y] = particle["data-implant-site"].split(" ").map(Number);
      rows.set(y, [...(rows.get(y) ?? []), x]);
      expect(particle.r).toBe("1.2");
      if (
        Number(particle.cy) > patternSurfaceHeight(state, x, y) + 0.1 &&
        Number(particle.cy) < beamTop - 2
      ) {
        incoming++;
        expect(Number(particle.opacity)).toBeCloseTo(1);
      }
    }
    expect(incoming).toBeGreaterThan(0);
    expect(rows.size).toBe(4);
    for (const xs of rows.values()) {
      expect(xs).toHaveLength(13);
      for (let i = 1; i < xs.length; i++) expect(xs[i] - xs[i - 1]).toBe(8);
    }
  },
);

it.each([stages.well, stages.implant, stages.implantP])(
  "shows ions clearly below the silicon surface on the cut face without drawing buried ions over opaque surfaces, scene %i",
  (index) => {
    let visiblyBuried = false;
    for (let sample = 1; sample < 20; sample++) {
      const { markup, state } = render(index, sample / 20);
      for (const particle of implantParticles(markup)) {
        const [x, y] = particle["data-implant-site"].split(" ").map(Number);
        if (particle["data-implant-target"] !== "silicon") continue;
        const depth = siliconSurfaceHeight(x, y, state) - Number(particle.cy);
        if (depth < 1) continue;
        if (particle["data-implant-cut-face"] === "true") {
          if (depth > (index === stages.well ? 8 : 3))
            visiblyBuried ||= Number(particle.opacity) > 0.8;
        } else expect(Number(particle.opacity)).toBe(0);
      }
    }
    expect(visiblyBuried).toBe(true);
  },
);

it.each([stages.well, stages.implant, stages.implantP])(
  "keeps whole-wafer implantation distinct from growing surface impacts, scene %i",
  (index) => {
    const { state, visit } = render(index, 0.4);
    const markup = renderToStaticMarkup(
      createElement(WaferProcessEffects, { index, state, visit }),
    );
    expect(markup.match(/data-wafer-implant/g)).toHaveLength(28);
    expect(markup).not.toContain("<ellipse");
  },
);

it.each([stages.well, stages.implant, stages.implantP])(
  "stops implant particles at masks and gates while exposed silicon receives dopants, scene %i",
  (index) => {
    const targets = new Set<string>();
    let penetrates = false;
    let deep = false;
    for (const progress of [0.2, 0.4, 0.6, 0.8]) {
      const { markup, state } = render(index, progress);
      for (const [tag] of markup.matchAll(
        /<circle\b[^>]*data-implant-site="[^"]+"[^>]*>/g,
      )) {
        const attrs = Object.fromEntries(
          [...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map(([, key, value]) => [
            key,
            value,
          ]),
        );
        const [x, y] = attrs["data-implant-site"].split(" ").map(Number);
        const z = Number(attrs.cy);
        const target = attrs["data-implant-target"];
        targets.add(target);
        if (target !== "silicon") {
          expect(z).toBeGreaterThanOrEqual(
            patternSurfaceHeight(state, x, y) - 1e-8,
          );
        } else if (Number(attrs.opacity) > 0.02) {
          penetrates ||= z < siliconSurfaceHeight(x, y, state);
          deep ||= z < siliconSurfaceHeight(x, y, state) - 8;
        }
      }
    }
    expect(targets.has("photoresist")).toBe(true);
    expect(targets.has("silicon")).toBe(true);
    expect(penetrates).toBe(true);
    if (index === stages.well) expect(deep).toBe(true);
    else expect(targets.has("gate")).toBe(true);
  },
);

it.each([
  stages.prepareIsolation,
  stages.patternGate,
  stages.contacts,
  stages.metalPattern,
  stages.via,
  stages.upperMetalPattern,
])(
  "bombards protected and open etch areas, ejecting material only from openings, scene %i",
  (index) => {
    let protectedSites = 0;
    let removalSites = 0;
    let fragments = 0;
    for (const progress of [0.2, 0.4, 0.6]) {
      const { markup } = render(index, progress);
      for (const site of markup.split('<g data-surface-site="').slice(1)) {
        if (site.includes('data-etch-blocked="true"')) {
          protectedSites++;
          expect(site).not.toContain('data-etch-fragment="true"');
        } else {
          removalSites++;
          if (site.includes('data-etch-fragment="true"')) fragments++;
        }
      }
    }
    expect(protectedSites).toBeGreaterThan(0);
    expect(removalSites).toBeGreaterThan(0);
    expect(fragments).toBeGreaterThan(0);
  },
);

it("uses the repeated wafer mask to protect the whole-wafer view during etching", () => {
  const index = stages.patternGate;
  const { state, visit } = render(index, 0.4);
  const markup = renderToStaticMarkup(
    createElement(WaferProcessEffects, { index, state, visit }),
  );
  expect(markup).toContain('data-etch-blocked="true"');
  expect(markup).toContain('data-etch-fragment="true"');
});

it("settles without lingering particles once processing has finished", () => {
  const index = stages.well;
  const { state, visit } = render(index, 1);
  visit.working = false;
  expect(
    renderToStaticMarkup(
      createElement(CloseupProcessEffects, {
        index,
        state,
        visit,
        ymax: 34,
        project: ([x, , z]) => [x, z],
      }),
    ),
  ).toBe("");
  expect(
    renderToStaticMarkup(
      createElement(WaferProcessEffects, { index, state, visit }),
    ),
  ).toBe("");
});
