import { describe, expect, it } from "vitest";
import { WizardError } from "../src/errors.js";
import { parseJsonc, stripJsonc } from "../src/jsonc.js";

describe("JSONC parsing", () => {
  it("removes comments and trailing commas", () => {
    const text = `{
      // line comment
      "a": 1, /* block */
      "b": [1, 2,],
    }`;

    expect(JSON.parse(stripJsonc(text))).toEqual({ a: 1, b: [1, 2] });
  });

  it("keeps comment and comma sequences inside strings", () => {
    const value = {
      glob: "src/**/*.ts",
      url: "https://example.com//path",
      literal: "a,}",
      escaped: 'quote \\" /* not a comment */',
    };

    expect(JSON.parse(stripJsonc(JSON.stringify(value)))).toEqual(value);
  });

  it("names the file when the text is not JSON", () => {
    expect(() => parseJsonc("/home/u/opencode.json", "[1,")).toThrow(
      new WizardError(
        "/home/u/opencode.json is not valid JSONC. Fix or move it.",
      ),
    );
    expect(() => parseJsonc("/home/u/opencode.json", "[]")).toThrow(
      "does not contain a JSON object",
    );
  });

  it("reads an empty or comment-only file as an empty object", () => {
    expect(parseJsonc("/x", "  // nothing yet\n")).toEqual({});
  });
});
