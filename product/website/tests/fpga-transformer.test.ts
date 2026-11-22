import { describe, expect, it } from "vitest";
import {
  cacheSnapshot,
  encodeRequest,
  requestSnapshot,
  requestProjectionSnapshot,
  textRequest,
  nextCacheCommit,
  projectionSnapshot,
  roundToEven,
  transformerExample as data,
} from "../../../hardware/publishing/sand-to-thought/articles/fpga/figures/transformerModel";

describe("Recorded tiny-transformer article examples", () => {
  it("preserves both recorded projections, including scale conversion and output capture", () => {
    for (const [rowIndex, row] of data.projection.rows.entries()) {
      let sum = 0;
      expect(projectionSnapshot(rowIndex, 0)).toMatchObject({
        sum: 0,
        output: null,
        cycle: null,
      });
      for (let i = 0; i < 32; i++) {
        const product = data.projection.inputs[i] * row.weights[i];
        sum += product;
        expect(row.products[i]).toBe(product);
        expect(projectionSnapshot(rowIndex, i + 1)).toMatchObject({
          sum,
          output: null,
          coordinate: i,
          cycle: row.cycles[i],
        });
      }
      expect(
        roundToEven(
          sum,
          data.projection.outputExponent - data.projection.sumExponent,
        ),
      ).toBe(row.result);
      expect(projectionSnapshot(rowIndex, 33)).toMatchObject({
        output: row.result,
        cycle: row.resultCycle,
      });
      expect(row.resultCycle).toBeGreaterThan(row.cycles[31]);
      expect(
        row.cycles.some((cycle, i) => i > 0 && cycle - row.cycles[i - 1] > 1),
      ).toBe(true);
    }
    expect(projectionSnapshot(0, 1)).toMatchObject({
      input: -1779,
      weight: -3900,
      product: 6938100,
    });
    expect(projectionSnapshot(0, 33)).toMatchObject({
      sum: -3760136,
      output: -115,
    });
    expect(-115 * 2 ** data.projection.outputExponent).toBe(-0.05615234375);
  });

  it("rounds negative and positive ties to even", () => {
    expect([3, 5, 7, -3, -5, -7].map((value) => roundToEven(value, 1))).toEqual(
      [2, 2, 4, -2, -2, -4],
    );
  });

  it("keeps all partial tokens unreadable until their final pair is recorded", () => {
    let previousCount = 0;
    for (const [index, frame] of data.cache.frames.entries()) {
      if (!frame.write) continue;
      const [position, coordinate, k, v] = frame.write;
      const snapshot = cacheSnapshot("writes", index, position, coordinate);
      expect(snapshot.pair).toEqual([k, v]);
      expect(snapshot.readable).toBe(coordinate === 31);
      expect(frame.count).toBe(previousCount + Number(coordinate === 31));
      expect(snapshot.pair).toEqual(data.cache.fullReadback[snapshot.address]);
      previousCount = frame.count;
    }
    let index = 0;
    for (const count of [1, 2, 3]) {
      index = nextCacheCommit(index);
      expect(data.cache.frames[index].count).toBe(count);
    }
    expect(nextCacheCommit(index)).toBe(index);
  });

  it("retains the same physical bits after reset, but refuses every position", () => {
    expect(data.cache.fullReadback).toHaveLength(256 * 32);
    expect(256 * 32 * 2 * 2).toBe(32768);
    for (let position = 0; position < 256; position++) {
      for (let coordinate = 0; coordinate < 32; coordinate++) {
        const before = cacheSnapshot("full", 0, position, coordinate);
        const after = cacheSnapshot("reset", 0, position, coordinate);
        expect(before.readable).toBe(true);
        expect(after.readable).toBe(false);
        expect(after.pair).toEqual(before.pair);
      }
    }
    expect(cacheSnapshot("reset", 0, 255, 31).address).toBe(8191);
    expect(cacheSnapshot("writes", 0, 255, 31).pair).toBeUndefined();
  });

  it("rejects selections beyond the excerpt and physical cache", () => {
    expect(() => projectionSnapshot(2, 0)).toThrow();
    expect(() => projectionSnapshot(0, 34)).toThrow();
    expect(() => cacheSnapshot("writes", 0, 256, 0)).toThrow();
    expect(() => cacheSnapshot("writes", 0, 0, 32)).toThrow();
  });
});

describe("Actual-text transformer request", () => {
  it("encodes every UTF-8 byte losslessly without selecting a response", () => {
    for (const input of ["", "fu2p2q", "hello", "🙂", "chip\n\t"]) {
      const tokens = encodeRequest(input);
      expect(tokens[0]).toBe(256);
      const decoded = [];
      for (let i = 1; i < tokens.length; i += 2) {
        expect(tokens[i]).toBeGreaterThanOrEqual(272);
        expect(tokens[i]).toBeLessThan(288);
        expect(tokens[i + 1]).toBeGreaterThanOrEqual(288);
        expect(tokens[i + 1]).toBeLessThan(304);
        decoded.push((tokens[i] - 272) * 16 + tokens[i + 1] - 288);
      }
      expect(new TextDecoder().decode(Uint8Array.from(decoded))).toBe(input);
    }
    expect(encodeRequest("a")).toEqual([256, 278, 289]);
    expect(encodeRequest(textRequest.input)).toEqual(textRequest.tokens);
    expect(encodeRequest("a".repeat(48))).toHaveLength(97);
    expect(() => encodeRequest("a".repeat(49))).toThrow();
    expect(() => encodeRequest("🙂".repeat(13))).toThrow();
  });

  it("uses complete score vectors for two verified predictions from the same request", () => {
    for (const [index, prediction] of textRequest.predictions.entries()) {
      expect(prediction.scores).toHaveLength(320);
      const largest = Math.max(...prediction.scores);
      expect(prediction.scores.indexOf(largest)).toBe([82, 101][index]);
      expect(
        prediction.scores.filter((score) => score === largest),
      ).toHaveLength(1);
      expect(prediction.winner).toBe(textRequest.outputTokens[index]);
      expect(prediction.position).toBe(index + 2);
      for (const vector of Object.values(prediction.vectors)) {
        expect(vector).toHaveLength(32);
        expect(vector.every(Number.isInteger)).toBe(true);
      }
      expect(prediction.attentionWeights).toHaveLength(index + 3);
    }
    expect(
      new TextDecoder().decode(Uint8Array.from(textRequest.outputTokens)),
    ).toBe(textRequest.output);
    expect(textRequest.output.startsWith("Resist development")).toBe(true);
    expect(textRequest.predictions[1].inputToken).toBe(
      textRequest.predictions[0].winner,
    );
    expect(textRequest.source.goldensSha256).toMatch(/^[a-f0-9]{64}$/);
    expect(textRequest.source.incrementalMatchesFull).toBe(true);
  });

  it("retains context and separates supplied input, first choice and next prediction", () => {
    expect(requestSnapshot(0)).toMatchObject({ cacheCount: 0, output: "" });
    expect(requestSnapshot(1).cacheCount).toBe(2);
    expect(requestSnapshot(5).cacheCount).toBe(3);
    expect(requestSnapshot(9)).toMatchObject({
      cacheCount: 3,
      winner: 82,
      output: "R",
    });
    expect(requestSnapshot(10)).toMatchObject({ cacheCount: 3, output: "R" });
    expect(requestSnapshot(11)).toMatchObject({
      cacheCount: 4,
      winner: 101,
      output: "R",
    });
    expect(requestSnapshot(12)).toMatchObject({ output: "Re" });
    expect(requestSnapshot(2).vector).toEqual(
      textRequest.predictions[0].vectors.embed,
    );
    expect(requestSnapshot(10).vector).toEqual(
      textRequest.predictions[1].vectors.embed,
    );
    expect(requestSnapshot(13).vector).toBeUndefined();
    for (const invalid of [-1, 14, 0.5])
      expect(() => requestSnapshot(invalid)).toThrow();
  });

  it("reconstructs two query coordinates with shared arithmetic and only saves after addition", () => {
    const projection = textRequest.projection;
    for (const [rowIndex, row] of projection.rows.entries()) {
      let sum = 0;
      for (let i = 0; i < 32; i++) {
        const product = projection.inputs[i] * row.weights[i];
        expect(row.products[i]).toBe(product);
        expect(requestProjectionSnapshot(rowIndex, i * 3 + 1)).toMatchObject({
          phase: "read",
          coordinate: i,
          sum,
          product: null,
          output: null,
        });
        expect(requestProjectionSnapshot(rowIndex, i * 3 + 2)).toMatchObject({
          phase: "multiply",
          sum,
          product,
          output: null,
        });
        sum += product;
        expect(requestProjectionSnapshot(rowIndex, i * 3 + 3)).toMatchObject({
          phase: "save",
          sum,
          output: null,
        });
      }
      const result = roundToEven(
        sum,
        projection.outputExponent -
          projection.inputExponent -
          projection.weightExponent,
      );
      expect(result).toBe(row.result);
      expect(result).toBe(textRequest.predictions[0].vectors.q[rowIndex]);
      expect(requestProjectionSnapshot(rowIndex, 97).output).toBe(result);
    }
    expect(requestProjectionSnapshot(0, 0).sum).toBe(0);
    expect(requestProjectionSnapshot(1, 0).sum).toBe(0);
    for (const [row, step] of [
      [2, 0],
      [0, 98],
      [0, -1],
    ])
      expect(() => requestProjectionSnapshot(row, step)).toThrow();
  });
});
