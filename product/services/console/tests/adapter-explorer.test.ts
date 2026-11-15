import { describe, expect, it } from "vitest";

import { buildDeckLayout } from "../src/components/adapter-explorer/layout";
import {
  buildExplorerModel,
  moduleGroup,
  moduleLabel,
  type AdapterWeights,
} from "../src/components/adapter-explorer/model";

const heatmap = (bytes: number[]) => btoa(String.fromCharCode(...bytes));

const module = (
  layer: number | null,
  name: string,
  norm: number,
  shape: [number, number] = [8, 4],
): AdapterWeights["modules"][number] => ({
  module: name,
  layer,
  shape,
  experts: 1,
  rank: 2,
  norm,
  singular_values: [norm * 0.8, norm * 0.6],
  heatmap_shape: [2, 2],
  heatmap: heatmap([255, 0, 128, 64]),
  heatmap_max: norm / 2,
});

const weights = (modules: AdapterWeights["modules"]): AdapterWeights => ({
  rank: 2,
  alpha: 4,
  scale: 2,
  parameters: 1000,
  modules,
});

describe("adapter explorer model", () => {
  it("joins the base layout with the adapter and measures update shares", () => {
    const model = buildExplorerModel(
      weights([
        module(1, "self_attn.q_proj", 3),
        module(null, "lm_head", 4, [32, 4]),
      ]),
      {
        layerCount: 3,
        expertCount: 8,
        expertLayers: [1, 2],
        projectionShapes: {
          "0/self_attn.q_proj": [8, 4],
          "0/mlp.down_proj": [4, 16],
          "1/self_attn.q_proj": [8, 4],
          "1/mlp.down_proj": [4, 16],
          "2/self_attn.q_proj": [8, 4],
          "2/mlp.down_proj": [4, 16],
          lm_head: [32, 4],
        },
      },
    );

    expect(model.layerCount).toBe(3);
    expect(model.modules).toHaveLength(7);
    expect(model.layers.map((layer) => layer.experts)).toEqual([0, 8, 8]);
    expect(model.ranked.map((entry) => entry.key)).toEqual([
      "lm_head",
      "1/self_attn.q_proj",
    ]);
    expect(model.head).toMatchObject({ adapted: true, share: 16 / 25 });
    expect(model.layers[1]!.share).toBeCloseTo(9 / 25);
    expect(model.layers[0]!.share).toBe(0);
    expect(model.adaptedLayers).toBe(1);
    expect(model.groupShares).toMatchObject({
      attention: 9 / 25,
      head: 16 / 25,
    });
    expect([...model.head!.heatmap!.values]).toEqual([255, 0, 128, 64]);
    const frozen = model.modules.find(
      (entry) => entry.key === "0/mlp.down_proj",
    )!;
    expect(frozen).toMatchObject({ adapted: false, norm: 0, intensity: 0 });
  });

  it("falls back to the adapter's own modules when the base layout is unknown", () => {
    const model = buildExplorerModel(
      weights([
        module(4, "self_attn.q_b_proj", 1, [18_432, 1536]),
        { ...module(4, "mlp.experts.down_proj", 1), experts: 896 },
      ]),
    );
    expect(model.layerCount).toBe(5);
    expect(model.expertCount).toBe(896);
    expect(model.structureKnown).toBe(false);
    expect(model.modules.map((entry) => entry.group)).toEqual([
      "attention",
      "experts",
    ]);
  });

  it("names and groups projections", () => {
    expect(moduleLabel("ffn.shared_experts.w1")).toBe("shared_experts.w1");
    expect(moduleLabel("self_attn.kv_a_proj_with_mqa")).toBe(
      "kv_a_proj_with_mqa",
    );
    expect(moduleGroup("attn.wq_b")).toBe("attention");
    expect(moduleGroup("ffn.shared_experts.w2")).toBe("mlp");
    expect(moduleGroup("mlp.experts.gate_up_proj")).toBe("experts");
  });
});

describe("adapter explorer layout", () => {
  it("places every projection inside its plate and an expert grid on MoE layers", () => {
    const model = buildExplorerModel(
      weights([module(1, "self_attn.q_proj", 1)]),
      {
        layerCount: 93,
        expertCount: 896,
        expertLayers: Array.from({ length: 92 }, (_, layer) => layer + 1),
        projectionShapes: Object.fromEntries(
          Array.from({ length: 93 }, (_, layer) => [
            [`${layer}/self_attn.q_proj`, [12_288, 7168]],
            [`${layer}/self_attn.o_proj`, [7168, 12_288]],
          ]).flat(),
        ),
      },
    );
    const deck = buildDeckLayout(model);

    expect(deck.plates).toHaveLength(95);
    expect(deck.plates[0]!.kind).toBe("embedding");
    expect(deck.plates.at(-1)!.kind).toBe("head");
    expect(deck.plates[1]!.experts).toBeUndefined();
    expect(deck.plates[2]!.experts).toMatchObject({ count: 896 });
    expect(deck.panels).toHaveLength(186);
    for (const plate of deck.plates) {
      const xs = plate.panels.map((panel) => panel.plate);
      expect(new Set(xs).size).toBeLessThanOrEqual(1);
      for (const panel of plate.panels) {
        expect(Math.abs(panel.u) + panel.width / 2).toBeLessThanOrEqual(
          plate.width / 2 + 1e-9,
        );
        expect(Math.abs(panel.v) + panel.height / 2).toBeLessThanOrEqual(
          plate.height / 2 + 1e-9,
        );
      }
      if (plate.experts) {
        const pitch = plate.experts.size + plate.experts.gap;
        expect(
          plate.experts.columns * plate.experts.rows,
        ).toBeGreaterThanOrEqual(plate.experts.count);
        expect(
          Math.abs(plate.experts.v) + (plate.experts.rows * pitch) / 2,
        ).toBeLessThanOrEqual(plate.height / 2 + pitch);
      }
    }
    expect(
      deck.plates
        .slice(1, -1)
        .every((plate, index, plates) =>
          index === 0 ? true : plate.x > plates[index - 1]!.x,
        ),
    ).toBe(true);
  });
});
