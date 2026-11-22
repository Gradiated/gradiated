import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { WholeWafer } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/FabricationLab";
import { expect, it } from "vitest";
import { scenes } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/model";
import {
  initialOpening,
  openingState,
  WaferTransfer,
} from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/FabricationIntroduction";
import {
  patternState,
  stages,
  visitFor,
} from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/process";
import { steps } from "../../../hardware/publishing/sand-to-thought/articles/fabricating-a-transistor/figures/sequence";

it("keeps every introductory view on bare silicon until processing begins", () => {
  expect(scenes.map((scene) => scene.key)).toEqual(
    steps.map((step) => step.key),
  );
  for (let index = stages.wafer; index < stages.growOxide; index++) {
    const state = patternState(index, visitFor(1, undefined, undefined));
    expect(Object.values(state).every((value) => value === 0)).toBe(true);
  }
  const oxide = patternState(
    stages.growOxide,
    visitFor(0.6, "furnace", undefined),
  );
  expect(oxide.oxide).toBeGreaterThan(0);
  expect(oxide.oxide).toBeLessThan(1);
  expect(oxide.well).toBe(0);
  expect(oxide.poly).toBe(0);
});

it("reveals the wafer, empty room, empty-handed operator and linked views in order", () => {
  const wafer = openingState(stages.wafer, 1, initialOpening);
  expect(wafer).toMatchObject({
    wafer: 1,
    centred: 1,
    room: 0,
    operator: 0,
    magnify: 0,
  });
  const room = openingState(stages.cleanRoom, 1, wafer);
  expect(room).toMatchObject({
    centred: 0,
    gloves: 1,
    room: 1,
    operator: 0,
    machines: 0,
  });
  const operator = openingState(stages.operator, 1, room);
  expect(operator).toMatchObject({
    operator: 1,
    entry: 1,
    transfer: 0,
    magnify: 0,
  });
  const handOff = openingState(stages.handOff, 1, operator);
  expect(handOff).toMatchObject({ transfer: 1, magnify: 0, machines: 0 });
  const magnify = openingState(stages.magnify, 1, handOff);
  expect(magnify).toMatchObject({ magnify: 1, machines: 0 });
  expect(openingState(stages.layout, 1, magnify).machines).toBe(1);
});

it("starts a skipped or reversed transition from the currently displayed view", () => {
  const interrupted = openingState(
    stages.cleanRoom,
    0.45,
    openingState(stages.wafer, 1, initialOpening),
  );
  expect(openingState(0, 0, interrupted)).toEqual(interrupted);
  const expanded = openingState(stages.layout, 1, initialOpening);
  expect(openingState(stages.wafer, 0, expanded)).toEqual(expanded);
  expect(openingState(stages.wafer, 1, expanded)).toEqual(
    openingState(stages.wafer, 1, initialOpening),
  );
});

it("finishes earlier opening movements as soon as the reader passes their sections", () => {
  const floating = openingState(
    stages.cleanRoom,
    0.2,
    openingState(stages.wafer, 1, initialOpening),
  );
  expect(floating.centred).toBeGreaterThan(0);
  const operator = openingState(stages.operator, 0, floating);
  expect(operator).toMatchObject({
    centred: 0,
    wafer: 1,
    gloves: 1,
    room: 1,
    destination: 0,
  });
  expect(openingState(stages.growOxide, 0, initialOpening)).toEqual(
    openingState(stages.growOxide, 1, initialOpening),
  );
});

it("hides the gloves only when a real machine has the wafer loaded", () => {
  const state = patternState(stages.wafer, visitFor(1, undefined, undefined));
  for (const machine of [undefined, "furnace"] as const) {
    const visit = visitFor(0.6, machine, undefined);
    expect(visit.loaded).toBe(1);
    const markup = renderToStaticMarkup(
      createElement(WholeWafer, {
        index: machine ? stages.growOxide : stages.operator,
        state,
        visit,
      }),
    );
    expect(markup).toContain(`class="fab-gloves" opacity="${machine ? 0 : 1}"`);
  }
  const visit = visitFor(1, "furnace", undefined);
  const markup = renderToStaticMarkup(
    createElement(WholeWafer, {
      index: stages.growOxide,
      state,
      visit,
    }),
  );
  expect(markup).toContain('class="fab-gloves" opacity="1"');
});

it("keeps an interrupted handoff wafer out of unrelated figures when scrolling backwards", () => {
  const state = patternState(stages.wafer, visitFor(1, undefined, undefined));
  const layout = {
    dx: 0,
    dy: 0,
    scale: 1,
    source: { x: 100, y: 300, rx: 95, ry: 76 },
    target: { x: 300, y: 100, rx: 8, ry: 5 },
  };
  const renderTransfer = (index: number, fromIndex: number, progress: number) =>
    renderToStaticMarkup(
      createElement(WaferTransfer, {
        index,
        fromIndex,
        progress,
        layout,
        state,
      }),
    );

  for (const index of [
    0,
    stages.wafer,
    stages.cleanRoom,
    stages.magnify,
    stages.inverter,
  ]) {
    for (const progress of [0.1, 0.5, 0.9]) {
      expect(renderTransfer(index, stages.handOff, progress)).toBe("");
    }
  }
  expect(renderTransfer(stages.operator, stages.growOxide, 0.5)).toBe("");
  expect(renderTransfer(stages.handOff, stages.operator, 0.5)).toContain(
    'class="fab-wafer-transfer"',
  );
  expect(renderTransfer(stages.operator, stages.handOff, 0.5)).toContain(
    'class="fab-wafer-transfer"',
  );
  expect(renderTransfer(stages.handOff, stages.operator, 0)).toBe("");
  expect(renderTransfer(stages.handOff, stages.operator, 1)).toBe("");
});
