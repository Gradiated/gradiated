import assert from "node:assert/strict";
import { test } from "node:test";
import { withFreshTokenRetry } from "./api.mjs";

const rejected = (statusCode) =>
  Object.assign(new Error("rejected"), { statusCode });

test("a renewed token can become visible after its first authorization rejection", async () => {
  let calls = 0;
  let now = 1000;
  const result = await withFreshTokenRetry(
    async () => {
      if (++calls < 3) throw rejected(403);
      return "allocation checks";
    },
    now,
    undefined,
    {
      now: () => now,
      pause: async (ms) => {
        now += ms;
      },
    },
  );
  assert.equal(result, "allocation checks");
  assert.equal(calls, 3);
});

test("an authorization rejection remains fatal once the fresh-token window ends", async () => {
  let now = 0;
  let calls = 0;
  const error = rejected(403);
  await assert.rejects(
    withFreshTokenRetry(
      async () => {
        calls++;
        throw error;
      },
      0,
      undefined,
      {
        now: () => now,
        pause: async (ms) => {
          now += ms;
        },
      },
    ),
    (actual) => actual === error,
  );
  assert.equal(now, 10_000);
  assert.equal(calls, 41);
});

test("existing credentials do not hide an authorization failure", async () => {
  const error = rejected(403);
  await assert.rejects(
    withFreshTokenRetry(
      async () => {
        throw error;
      },
      -Infinity,
      undefined,
      {
        pause: async () => assert.fail("must not retry existing credentials"),
      },
    ),
    (actual) => actual === error,
  );
});

for (const error of [
  rejected(401),
  rejected(500),
  new Error("connection interrupted"),
]) {
  test(`does not replay an operation after ${error.statusCode ?? "an unknown outcome"}`, async () => {
    let calls = 0;
    await assert.rejects(
      withFreshTokenRetry(
        async () => {
          calls++;
          throw error;
        },
        Date.now(),
        undefined,
      ),
      (actual) => actual === error,
    );
    assert.equal(calls, 1);
  });
}

test("cancelling a fresh-token wait stops retries", async () => {
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(
    withFreshTokenRetry(
      async () => {
        throw rejected(403);
      },
      Date.now(),
      controller.signal,
    ),
    { name: "AbortError" },
  );
});
