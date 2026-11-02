import { expect, it } from "vitest";
import {
  interconnectLevels,
  interconnectSolids,
  inverterPlacement,
  type InterconnectSolid,
  type InterconnectNet,
} from "../src/components/articles/fabrication/interconnectLayout";
import {
  firstMetalTracks,
  upperMetalTracks,
} from "../src/components/articles/fabrication/process";

const { x, y, scale } = inverterPlacement;
const localWire = (
  id: string,
  net: InterconnectNet,
  layer: number,
  [x0, x1, y0, y1]: readonly number[],
): InterconnectSolid => ({
  id,
  net,
  layer,
  kind: "wire",
  x: x + x0 * scale,
  y: y + y0 * scale,
  z: interconnectLevels[layer].z,
  width: (x1 - x0) * scale,
  depth: (y1 - y0) * scale,
  height: interconnectLevels[layer].height,
});
const localNets: InterconnectNet[] = [
  "input",
  "output",
  "input",
  "output",
  "ground",
  "supply",
];
const localWires = [
  ...firstMetalTracks.map((track, index) =>
    localWire(`inverter-${index}`, localNets[index], 0, track),
  ),
  ...upperMetalTracks.map((track, index) =>
    localWire(`inverter-upper-${index}`, "output", 1, track),
  ),
];
const localVia: InterconnectSolid = {
  id: "inverter-via",
  net: "output",
  layer: 1,
  kind: "via",
  x: x + 48 * scale,
  y: y + 21 * scale,
  z: 17 * scale,
  width: 4 * scale,
  depth: 4 * scale,
  height: 8 * scale,
};
const solids = [...interconnectSolids, ...localWires, localVia];
const epsilon = 1e-8;
const touches = (a: InterconnectSolid, b: InterconnectSolid) =>
  a.x <= b.x + b.width + epsilon &&
  a.x + a.width >= b.x - epsilon &&
  a.y <= b.y + b.depth + epsilon &&
  a.y + a.depth >= b.y - epsilon &&
  a.z <= b.z + b.height + epsilon &&
  a.z + a.height >= b.z - epsilon;
const containsFootprint = (wire: InterconnectSolid, via: InterconnectSolid) =>
  wire.x <= via.x + epsilon &&
  wire.x + wire.width >= via.x + via.width - epsilon &&
  wire.y <= via.y + epsilon &&
  wire.y + wire.depth >= via.y + via.depth - epsilon;

it("lands every via fully on a wire of the same net at both ends", () => {
  const wires = solids.filter((solid) => solid.kind === "wire");
  for (const via of solids.filter((solid) => solid.kind === "via")) {
    const lower = wires.filter(
      (wire) =>
        wire.layer === via.layer - 1 &&
        wire.net === via.net &&
        containsFootprint(wire, via),
    );
    const upper = wires.filter(
      (wire) =>
        wire.layer === via.layer &&
        wire.net === via.net &&
        containsFootprint(wire, via),
    );
    expect(
      lower.some((wire) => Math.abs(wire.z + wire.height - via.z) < epsilon),
      via.id,
    ).toBe(true);
    expect(
      upper.some((wire) => Math.abs(wire.z - via.z - via.height) < epsilon),
      via.id,
    ).toBe(true);
  }
});

it("keeps the inverter input, output and two supply nets physically separate", () => {
  for (let a = 0; a < solids.length; a++) {
    for (let b = a + 1; b < solids.length; b++) {
      if (solids[a].net === solids[b].net) continue;
      expect(
        touches(solids[a], solids[b]),
        `${solids[a].id} touches ${solids[b].id}`,
      ).toBe(false);
    }
  }
});

it("connects each actual inverter terminal through the stack without floating routes", () => {
  for (const net of ["ground", "input", "supply", "output"] as const) {
    const members = solids.filter((solid) => solid.net === net);
    const visited = new Set([members[0]]);
    const queue = [members[0]];
    while (queue.length) {
      const current = queue.pop()!;
      for (const next of members) {
        if (visited.has(next) || !touches(current, next)) continue;
        visited.add(next);
        queue.push(next);
      }
    }
    expect(visited.size, net).toBe(members.length);
    expect(
      [...visited].some((solid) => solid.id.startsWith("inverter-")),
      net,
    ).toBe(true);
    expect(
      [...visited].some((solid) => solid.layer === 8),
      net,
    ).toBe(true);
  }
});

it("separates crossing metal levels with positive dielectric gaps", () => {
  interconnectLevels.slice(1).forEach((level, index) => {
    const below = interconnectLevels[index];
    expect(level.z - below.z - below.height).toBeGreaterThan(0);
  });
});
