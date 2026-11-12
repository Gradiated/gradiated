import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { describe, it } from "node:test";
import { model } from "./testing.ts";
import { Watchlist } from "./watchlist.ts";

describe("Watchlist", () => {
  it("parses the checked-in watchlist.json", async () => {
    const file = new URL("./watchlist.json", import.meta.url);
    const watchlist = Watchlist.parse(JSON.parse(await readFile(file, "utf8")));
    assert.ok(watchlist.labs.length > 0);
  });

  it("lists each owner once per source", () => {
    const watchlist = Watchlist.parse([
      {
        lab: "Google Gemma",
        huggingface: ["google"],
        openrouter: ["google"],
        include: ["gemma"],
      },
      { lab: "Google Gemini", openrouter: ["Google"], include: ["gemini"] },
    ]);
    assert.deepEqual(watchlist.owners("Hugging Face"), ["google"]);
    assert.deepEqual(watchlist.owners("OpenRouter"), ["google"]);
  });

  it("matches a model to the labs whose owner and filter fit", () => {
    const watchlist = Watchlist.parse([
      { lab: "Google Gemma", openrouter: ["google"], include: ["gemma"] },
      { lab: "Google Gemini", openrouter: ["google"], include: ["Gemini"] },
      { lab: "Qwen", openrouter: ["qwen"] },
    ]);
    const labs = (id: string) =>
      watchlist.labsFor("OpenRouter", model(id)).map(({ lab }) => lab);
    assert.deepEqual(labs("google/gemma-4-31b"), ["Google Gemma"]);
    assert.deepEqual(labs("google/gemini-4-carbon"), ["Google Gemini"]);
    assert.deepEqual(labs("google/lyria-3"), []);
    assert.deepEqual(labs("qwen/qwen3.8-27b"), ["Qwen"]);
    assert.deepEqual(
      watchlist.labsFor("Hugging Face", model("qwen/qwen3.8-27b")),
      [],
    );
  });

  for (const [why, json, message] of [
    ["not a list", {}, /must be a list of labs/],
    ["no lab name", [{ openrouter: ["x"] }], /Entry 1 needs a "lab" name/],
    [
      "a duplicate lab",
      [
        { lab: "A", openrouter: ["a"] },
        { lab: "A", openrouter: ["b"] },
      ],
      /"A" is listed twice/,
    ],
    [
      "an unknown field",
      [{ lab: "A", openrouter: ["a"], hf: ["a"] }],
      /A: unknown field "hf"/,
    ],
    ["no orgs or prefixes", [{ lab: "A" }], /A: list at least one/],
    [
      "a name that is not a string",
      [{ lab: "A", huggingface: [1] }],
      /A: "huggingface" must be/,
    ],
    [
      "a name with spaces around it",
      [{ lab: "A", openrouter: [" a"] }],
      /A: "openrouter" must be/,
    ],
  ] as const) {
    it(`rejects ${why}`, () => {
      assert.throws(() => Watchlist.parse(json), message);
    });
  }
});
