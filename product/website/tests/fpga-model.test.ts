import { readFileSync } from "node:fs";
import {
  continuationFor,
  isLaterScene,
} from "../../../hardware/publishing/sand-to-thought/articles/fpga/figures/ChipContinuation";
import { applicationFor } from "../../../hardware/publishing/sand-to-thought/articles/fpga/figures/ApplicationEnvironments";
import { describe, expect, it } from "vitest";
import { measurements } from "../../../hardware/publishing/sand-to-thought/articles/fpga/figures/measurementData";
import publication from "../../../hardware/publishing/sand-to-thought/articles/fpga/results.json";
import { architectureStateFor } from "../../../hardware/publishing/sand-to-thought/articles/fpga/figures/ArchitectureTour";
import {
  videoFrame,
  videoStep,
  videoTile,
} from "../../../hardware/publishing/sand-to-thought/articles/fpga/figures/ledWallModel";
import {
  answers,
  address,
  combined,
  changedAnswers,
  writeAnswer,
  capturePair,
  initialPulse,
  lookup,
  pulseEdge,
  requestWidth,
  timingBudget,
} from "../../../hardware/publishing/sand-to-thought/articles/fpga/figures/model";
import {
  chapters,
  groups,
  measurementScenes,
  scenes,
} from "../../../hardware/publishing/sand-to-thought/articles/fpga/figures/scenes";

describe("FPGA teaching examples", () => {
  it("keeps the FPGA map after the network introduction except in the chip comparison", () => {
    const start = scenes.findIndex((scene) => scene.key === "neuron-map");
    expect(start).toBeGreaterThan(0);
    for (const scene of scenes.slice(0, start + 1)) {
      const deviceRecap = ["pins", "memory-roles", "our-board"].includes(
        scene.key,
      );
      expect(isLaterScene(scene.key), scene.key).toBe(deviceRecap);
    }
    for (const scene of scenes.slice(start + 1).filter((item) => item.group !== 6)) {
      expect(isLaterScene(scene.key), scene.key).toBe(true);
      expect(
        Boolean(continuationFor(scene.key) || applicationFor(scene.key)),
        scene.key,
      ).toBe(scene.key !== "chip-choices");
    }
    expect(continuationFor("block-ram")?.world).toBeUndefined();
    expect(continuationFor("arithmetic-blocks")?.world).toBeUndefined();
  });

  it("uses the address order AB and selects exactly one stored answer", () => {
    expect(answers.AND).toEqual([0, 0, 0, 1]);
    expect(answers.XOR).toEqual([0, 1, 1, 0]);
    expect(answers.OR).toEqual([0, 1, 1, 1]);
    for (const a of [0, 1] as const) {
      for (const b of [0, 1] as const) {
        expect(lookup("AND", a, b)).toBe(a & b);
        expect(lookup("OR", a, b)).toBe(a | b);
        expect(lookup("XOR", a, b)).toBe(a ^ b);
        for (const c of [0, 1] as const)
          expect(combined(a, b, c)).toBe((a & b) ^ c);
      }
    }
  });

  it("rewrites only the two changed answers, then reads OR without altering storage", () => {
    const original = [...answers.AND];
    let stored = answers.AND;
    expect(changedAnswers(stored, answers.OR)).toEqual([1, 2]);

    stored = writeAnswer(stored, 1, 1);
    expect(stored).toEqual([0, 1, 0, 1]);
    expect(answers.AND).toEqual(original);
    expect(changedAnswers(stored, answers.OR)).toEqual([2]);
    expect(stored[2]).toBe(0);

    stored = writeAnswer(stored, 2, 1);
    expect(changedAnswers(stored, answers.OR)).toEqual([]);
    const held = [...stored];
    for (const a of [0, 1] as const) {
      for (const b of [0, 1] as const) {
        expect(stored[2 * a + b]).toBe(a | b);
        expect(stored).toEqual(held);
      }
    }

    expect(changedAnswers(stored, answers.AND)).toEqual([1, 2]);
    expect(() => writeAnswer(stored, -1, 0)).toThrow();
    expect(() => writeAnswer(stored, 4, 0)).toThrow();
    expect(() => writeAnswer(stored, 1.5, 0)).toThrow();
  });

  it("captures both register inputs from the pre-edge state, including wrap-around", () => {
    expect(capturePair({ a: 3, b: 0 })).toEqual({ a: 4, b: 3 });
    expect(capturePair({ a: 15, b: 14 })).toEqual({ a: 0, b: 15 });
    expect(capturePair(capturePair({ a: 3, b: 0 }))).toEqual({ a: 5, b: 4 });
  });

  it("keeps registered PWM aligned with the newly captured count for every supported width", () => {
    for (let width = 0; width <= 16; width++) {
      let state = initialPulse(width);
      let high = 0;
      for (let interval = 0; interval < 32; interval++) {
        expect(state.count).toBe(interval % 16);
        expect(state.output).toBe(Number(state.count < width));
        high += state.output;
        state = pulseEdge(state);
      }
      expect(high).toBe(width * 2);
    }
  });

  it("applies pending width only at wrap, without comparing against the old width", () => {
    let state = initialPulse(4);
    for (let i = 0; i < 7; i++) state = pulseEdge(state);
    state = requestWidth(state, 16);
    expect(state.width).toBe(4);
    for (let i = 0; i < 8; i++) {
      state = pulseEdge(state);
      expect(state.width).toBe(4);
    }
    expect(state.count).toBe(15);
    state = pulseEdge(state);
    expect(state).toMatchObject({
      count: 0,
      width: 16,
      pending: 16,
      output: 1,
    });
    state = requestWidth(state, 0);
    for (let i = 0; i < 16; i++) state = pulseEdge(state);
    expect(state).toMatchObject({ count: 0, width: 0, output: 0 });
    expect(() => requestWidth(state, 17)).toThrow();
    expect(() => requestWidth(state, -1)).toThrow();
    expect(() => requestWidth(state, 1.5)).toThrow();
  });

  it("distributes every pixel to exactly one tile without changing row order", () => {
    for (const frame of [0, 1]) {
      const pixels = videoFrame(frame);
      const tiles = [0, 1, 2, 3].map((tile) => videoTile(pixels, tile));
      expect(
        tiles.every(
          (tile) => tile.length === 8 && tile.every((row) => row.length === 4),
        ),
      ).toBe(true);
      expect(
        pixels.map((_, row) => tiles.flatMap((tile) => tile[row])),
      ).toEqual(pixels);
    }
  });

  it("holds the displayed picture while receiving and arranging the next one", () => {
    expect([0, 1, 2].map((step) => videoStep(step).displayed)).toEqual([
      null,
      null,
      null,
    ]);
    expect([3, 4, 5, 6].map((step) => videoStep(step).displayed)).toEqual([
      0, 0, 0, 0,
    ]);
    expect(videoStep(7)).toEqual({ phase: 3, incoming: 1, displayed: 1 });
    expect(videoFrame(0)).not.toEqual(videoFrame(1));
    expect(videoFrame(2)).toEqual(videoFrame(0));
  });

  it("labels the setup budget by whether the path meets its deadline", () => {
    expect(timingBudget(7)).toMatchObject({ slack: -1, passes: false });
    expect(timingBudget(10)).toMatchObject({ slack: 2, passes: true });
  });

  it("preserves the written answer on hold and makes reverse or skipped scenes deterministic", () => {
    expect(architectureStateFor("stored-bit")).toMatchObject({
      cellValue: 0,
      access: false,
      bits: [0, 0, 0, 1],
    });
    expect(architectureStateFor("write-and-hold")).toMatchObject({
      cellValue: 1,
      access: true,
      bits: [0, 1, 0, 1],
    });
    expect(architectureStateFor("cell-hold")).toMatchObject({
      cellValue: 1,
      access: false,
      bits: [0, 1, 0, 1],
    });
    expect(architectureStateFor("lut").bits).toEqual(answers.OR);
    expect(architectureStateFor("stored-bit").bits).toEqual(answers.AND);
  });

  it("captures a result at an edge and holds it when the LUT input changes", () => {
    const ready = architectureStateFor("flip-flop");
    const captured = architectureStateFor("logic-block");
    const held = architectureStateFor("flip-flop-hold");
    expect(ready.bits[address(ready.a, ready.b)]).toBe(1);
    expect(ready).toMatchObject({ q: 0, captured: false });
    expect(captured).toMatchObject({ q: 1, captured: true });
    expect(held.bits[address(held.a, held.b)]).toBe(0);
    expect(held).toMatchObject({ q: 1, captured: true });
    expect(held.bits).toEqual(captured.bits);
    expect(architectureStateFor("clb-output-setting")).toEqual(held);
    expect(architectureStateFor("flip-flop")).toEqual(ready);
  });

  it("changes the selected route separately from the incoming data", () => {
    expect(architectureStateFor("routing-switch")).toMatchObject({
      route: 0,
      incoming: 0,
    });
    const changed = architectureStateFor("routing-change");
    const data = architectureStateFor("routing-input");
    expect(changed).toMatchObject({ route: 1, incoming: 0 });
    expect(data).toMatchObject({ route: 1, incoming: 1 });
    expect(data.bits).toEqual(changed.bits);
  });

  it("adds a sourced measurement point for each step and preserves the paired controls", () => {
    expect(measurements).toHaveLength(measurementScenes.length);
    expect(measurements.map((point) => point.controlStep)).toEqual([
      undefined, 0, 1, 2, 3, 4, 5, 5, 7, 8, 9, 10, 11, 12, 12,
    ]);
    for (const point of measurements) {
      expect(publication.runs.map((run) => run.path)).toContain(
        `hardware/research/inference/results/${point.runId}/run.json`,
      );
    }
  });

  it("reproduces the workload plot from the pinned per-request samples", () => {
    const outputBytes = { "encoded-hello": 90, "encoded-fu2p2q": 122, "encoded-max48": 104 };
    for (const [step, point] of measurements.entries()) {
      const file = new URL(`../../../hardware/research/inference/results/${point.runId}/run.json`, import.meta.url);
      const run: { metrics: { name: string; samples: number[] }[] } = JSON.parse(readFileSync(file, "utf8"));
      const samples = Object.fromEntries(run.metrics.map(({ name, samples }) => [name, samples]));
      const controlArm = samples["stock.energy_per_answer"] ? "stock" : "control";
      const arms = [[step === 0 ? controlArm : "candidate", point.value], [controlArm, point.control]] as const;

      for (const [arm, value] of arms) {
        if (!value) continue;
        const waits: number[] = [];
        let decodeTokens = 0;
        let decodeSeconds = 0;
        for (const [prompt, length] of Object.entries(outputBytes)) {
          const rates = samples[`${arm}.${prompt}.decode_bytes_per_second`];
          expect(rates).toHaveLength(6);
          waits.push(...samples[`${arm}.${prompt}.ttft_ms`]);
          for (const rate of rates) {
            decodeTokens += length - 1;
            decodeSeconds += (length - 1) / rate;
          }
        }

        expect(waits).toHaveLength(18);
        expect(value.ttftMs).toBeCloseTo(waits.reduce((a, b) => a + b, 0) / waits.length, 4);
        expect(value.decodeTps).toBeCloseTo(decodeTokens / decodeSeconds, 4);
        const blockEnergy = samples[`${arm}.energy_per_answer`];
        expect(blockEnergy).toHaveLength(3);
        expect(value.joulesPerToken).toBeCloseTo(blockEnergy.reduce((a, b) => a + b, 0) * 6 / (3 * 632), 8);
      }
    }
  });

  it("maps every prose scene to one reusable figure group and eleven chapters", () => {
    const keys = scenes.map((scene) => scene.key);
    expect([...keys].sort()).toEqual([...groups.flat()].sort());
    expect(new Set(keys).size).toBe(keys.length);
    expect(measurementScenes).toHaveLength(15);
    expect(chapters).toHaveLength(11);
    expect(keys.indexOf("rule-change")).toBeLessThan(keys.indexOf("why-fpgas"));
    expect(keys.indexOf("why-fpgas")).toBeLessThan(keys.indexOf("why-display"));
    expect(keys.indexOf("why-display")).toBeLessThan(
      keys.indexOf("why-prototype"),
    );
    expect(keys.indexOf("why-prototype")).toBeLessThan(
      keys.indexOf("stored-bit"),
    );
    for (const key of [
      "inside-chip",
      "clb-resources",
      "inside-clb",
      "truth-table",
      "selector",
      "stored-bit",
      "write-and-hold",
      "cell-hold",
      "lut",
      "flip-flop",
      "logic-block",
      "flip-flop-hold",
      "clb-output-setting",
      "routing-grid",
      "routing-switch",
      "routing-change",
      "configuration-map",
      "configuration-source",
      "configuration-distribute",
      "configuration-luts",
      "rule-change",
      "why-fpgas",
      "why-display",
      "why-prototype",
    ]) {
      expect(scenes.find((scene) => scene.key === key)?.group).toBe(0);
    }
    const tourOrder = [
      "why-prototype",
      "inside-chip",
      "clb-resources",
      "inside-clb",
      "truth-table",
      "selector",
      "stored-bit",
      "write-and-hold",
      "cell-hold",
      "lut",
      "flip-flop",
      "logic-block",
      "flip-flop-hold",
      "clb-output-setting",
      "routing-grid",
      "routing-switch",
      "routing-change",
      "configuration-map",
      "configuration-source",
      "configuration-distribute",
      "configuration-luts",
      "clock-network",
      "block-ram",
    ];
    expect(tourOrder.map((key) => keys.indexOf(key))).toEqual(
      tourOrder.map((key) => keys.indexOf(key)).sort((a, b) => a - b),
    );
    const routingIndex = keys.indexOf("routing-change");
    expect(keys.slice(routingIndex, routingIndex + 3)).toEqual([
      "routing-change",
      "configuration-map",
      "configuration-source",
    ]);
    expect(keys).not.toContain("routing-input");
    expect(keys).not.toContain("ip-blocks");
    expect(scenes.find((scene) => scene.key === "stored-bit")?.html).toContain(
      "/library/sand-to-thought/how-to-get-an-answer-out-of-sand/#sand-latch",
    );
    expect(keys.indexOf("arithmetic-blocks")).toBeLessThan(
      keys.indexOf("arithmetic-accumulate"),
    );
    expect(keys.indexOf("arithmetic-accumulate")).toBeLessThan(
      keys.indexOf("arithmetic-save"),
    );
    expect(keys.indexOf("arithmetic-save") + 1).toBe(
      keys.indexOf("arithmetic-next"),
    );
    expect(keys.indexOf("arithmetic-next")).toBeLessThan(
      keys.indexOf("memory-roles"),
    );
    expect(keys.indexOf("resource-columns")).toBeLessThan(
      keys.indexOf("neuron-map"),
    );
    expect(keys.indexOf("memory-roles") + 1).toBe(
      keys.indexOf("resource-columns"),
    );
    expect(
      chapters.find((chapter) => chapter.id === "fpga-transformer-cache-map")
        ?.label,
    ).toBe("Running a tiny transformer");
    const neuronChapter = chapters.find(
      (chapter) => chapter.id === "fpga-neuron-map",
    );
    expect(neuronChapter?.label).toBe("Our FPGA’s first neuron");
    expect(
      keys.slice(neuronChapter?.index, keys.indexOf("transformer-cache-map")),
    ).toEqual([
      "neuron-map",
      "network-layers",
      "network-sum",
      "network-products",
      "neuron-hardware",
      "neuron",
      "neuron-next",
    ]);
    expect(keys.slice(keys.indexOf("measuring-inference"))).toEqual([
      ...measurementScenes,
      "measure-ddr-weight",
      "measure-ddr-row",
      "measure-ddr-scores",
      "measure-ddr-prefetch",
      "measure-probability-div",
      "measure-feedforward-multiply",
      "measure-norm-multiply",
      "measure-norm-share",
      "measure-projection-reads",
      "measure-value-pair",
      "measure-clock-rate",
      "chip-choices",
    ]);
    expect(keys).not.toContain("built-in-timers");
    expect(keys).not.toContain("cpu-and-fpga");
    expect(scenes.at(-1)?.html).toContain("<h3>Choosing a chip for inference</h3>");
    expect(scenes.at(-1)?.html).toContain("estimated speed and energy");
    expect(chapters.at(-1)).toMatchObject({
      id: "fpga-measuring-inference",
      label: "Measuring inference on the KV260",
    });
    expect(
      keys.slice(
        keys.indexOf("transformer-cache-map"),
        keys.indexOf("measuring-inference"),
      ),
    ).toEqual([
      "transformer-cache-map",
      "transformer-cache",
      "token-journey",
      "our-board",
      "board-request",
    ]);
    expect(
      scenes.find((scene) => scene.key === "transformer-cache")?.html,
    ).toContain("the same weighted sum we saw in the neuron example");
    expect(
      scenes.find((scene) => scene.key === "token-journey")?.html,
    ).toContain('id="fpga-projection"');
    expect(scenes.every((scene) => !scene.html.includes("[@"))).toBe(true);
  });
});
