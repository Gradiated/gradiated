import { describe, expect, it } from "vitest";
import { selectScrollScene } from "../../../hardware/publishing/sand-to-thought/articles/fpga/figures/scrollScene";

const positions = (boundary: number) => [
  { index: 0, top: -900 },
  { index: 2, top: boundary },
  { index: 3, top: boundary + 500 },
];

describe("FPGA scroll scene selection", () => {
  it("holds the current diagram within the boundary tolerance in either direction", () => {
    for (const offset of [-11, -1, 0, 1, 11]) {
      expect(selectScrollScene(positions(300 + offset), 300, 0)).toBe(0);
      expect(selectScrollScene(positions(300 + offset), 300, 2)).toBe(2);
    }

    expect(selectScrollScene(positions(287), 300, 0)).toBe(2);
    expect(selectScrollScene(positions(313), 300, 2)).toBe(0);
  });

  it("keeps selection stable when the sticky figure and prose move together", () => {
    for (const height of [252.125, 290.921875, 420]) {
      expect(selectScrollScene(positions(height + 20), height + 32, 0)).toBe(2);
      expect(selectScrollScene(positions(height + 44), height + 32, 2)).toBe(2);
    }
  });

  it("jumps directly to the reached scene and skips optional prose sections", () => {
    expect(selectScrollScene(positions(-600), 300, 0)).toBe(3);
    expect(selectScrollScene(positions(900), 300, 3)).toBe(0);
    expect(selectScrollScene(positions(0), 300, 0)).toBe(2);
  });
});
