import assert from "node:assert/strict";
import test from "node:test";
import {
  ringState,
  visibleKeys,
  paddingState,
  activationPayload,
} from "../src/components/articles/gemma/models";

test("speculative commit matches sequential writes, including wraparound and zero acceptance", () => {
  for (let cursor = 0; cursor < 16; cursor++) {
    for (const depth of [1, 2, 4, 8]) {
      for (let accepted = 0; accepted <= depth; accepted++) {
        const state = ringState(cursor, depth, accepted);
        const reference = [...state.initial];
        for (let i = 0; i < accepted; i++)
          reference[(cursor + i) % 16] = 16 + i;
        assert.deepEqual(state.committed, reference);
        assert.equal(state.nextCursor, (cursor + accepted) % 16);
        assert.equal(state.backup.length, depth);
        for (let q = 0; q < depth; q++) {
          const keys = visibleKeys(q);
          assert.equal(keys.length, 16);
          assert.equal(keys.at(-1), 16 + q);
          for (const token of keys) {
            assert.ok(
              state.proposed.includes(token) ||
                state.backup.some((b) => b.token === token),
            );
          }
        }
      }
    }
  }
});

test("padding never exposes tail columns or future tokens", () => {
  for (const n of [1, 64, 65, 6005, 6016]) {
    const s = paddingState(n, n - 2, true);
    assert.equal(s.extent % 64, 0);
    assert.ok(s.extent >= n && s.extent - n < 64);
    assert.ok(s.columns.every((c) => c.kind !== "visible" || c.index < n - 1));
    assert.ok(
      s.columns.filter((c) => c.index >= n).every((c) => c.kind === "padding"),
    );
  }
  assert.equal(paddingState(6005, 6004, true).extra, 11);
});

test("payload labels represent sizes, not projected runtime", () => {
  assert.deepEqual(activationPayload(64), {
    activationKiB: 672,
    metadataBytes: 256,
  });
});
