export type InterconnectNet = "ground" | "input" | "supply" | "output";
export type InterconnectSolid = {
  id: string;
  net: InterconnectNet;
  layer: number;
  kind: "wire" | "via";
  x: number;
  y: number;
  z: number;
  width: number;
  depth: number;
  height: number;
};

export const inverterPlacement = { x: 90, y: 86.4, scale: 0.4 };
export const interconnectLevels = Array.from({ length: 9 }, (_, layer) => ({
  z: layer === 0 ? 5.6 : 10 + (layer - 1) * 17,
  height: layer < 2 ? 1.2 : layer < 5 ? 3 : 6,
  width: layer < 2 ? 1.6 : layer < 5 ? 4 : 7,
}));
const nets: InterconnectNet[] = ["ground", "input", "supply", "output"];
const horizontalRows = [12, 36, 60, 76];
const verticalColumns = [20, 60, 160, 220];
const solids: InterconnectSolid[] = [];
const wire = (
  id: string,
  net: InterconnectNet,
  layer: number,
  x: number,
  y: number,
  width: number,
  depth: number,
) => {
  const { z, height } = interconnectLevels[layer];
  solids.push({ id, net, layer, kind: "wire", x, y, z, width, depth, height });
};
const via = (
  id: string,
  net: InterconnectNet,
  layer: number,
  x: number,
  y: number,
) => {
  const lower = interconnectLevels[layer - 1];
  const size = layer < 2 ? 0.8 : 1.2;
  const z = lower.z + lower.height;
  solids.push({
    id,
    net,
    layer,
    kind: "via",
    x: x - size / 2,
    y: y - size / 2,
    z,
    width: size,
    depth: size,
    height: interconnectLevels[layer].z - z,
  });
};

interconnectLevels.forEach(({ width }, layer) => {
  nets.forEach((net, index) => {
    const x = verticalColumns[index];
    const y = horizontalRows[index];
    const extent = layer === 1 ? [84.8, 80.8, 80.8, 88][index] : 100;

    if (layer % 2 === 0) {
      const start = layer === 0 ? [0, 24, 0, 80][index] : 0;
      const end = layer === 0 ? [240, 196, 240, 232][index] : 240;
      wire(
        `track-${layer}-${net}`,
        net,
        layer,
        start,
        y - width / 2,
        end - start,
        width,
      );
    } else {
      wire(
        `track-${layer}-${net}`,
        net,
        layer,
        x - width / 2,
        0,
        width,
        extent,
      );
    }
    if (layer) via(`via-${layer}-${net}`, net, layer, x, y);
  });
});

wire("ground-port", "ground", 0, 95.6, 84, 1.6, 3.2);
wire("ground-fanout", "ground", 0, 19.2, 83.2, 78, 1.6);
via("ground-port-via", "ground", 1, 20, 84);
wire("input-port", "input", 0, 109.2, 80, 1.6, 7.2);
wire("input-fanout", "input", 0, 59.2, 79.2, 51.6, 1.6);
via("input-port-via", "input", 1, 60, 80);
wire("supply-port", "supply", 0, 122.8, 80, 1.6, 7.2);
wire("supply-fanout", "supply", 0, 122.8, 79.2, 38, 1.6);
via("supply-port-via", "supply", 1, 160, 80);
wire("output-port", "output", 1, 126, 86.4, 94.8, 1.6);

export const interconnectSolids: readonly InterconnectSolid[] = solids;
