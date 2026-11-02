import { describe, expect, it } from "vitest";

import { matchesWholeAnswer } from "./whole-answer.js";

describe("whole visible answer comparison", () => {
  it.each([
    "tamarind",
    "Tamarind.",
    " **tamarind** ",
    "__tamarind__.",
    "`tamarind`",
    "**tamarind.**",
  ])("accepts harmless whole-marker formatting %s", (answer) => {
    expect(matchesWholeAnswer(answer, "tamarind")).toBe(true);
  });

  it.each(["1517", "1,517", "**1,517**.", "`1517.`", "__221__"])(
    "accepts exact arithmetic with valid formatting %s",
    (answer) => {
      expect(
        matchesWholeAnswer(answer, answer.includes("221") ? "221" : "1517"),
      ).toBe(true);
    },
  );

  it.each([
    "tamari",
    "tamarind wrong",
    "The answer is tamarind",
    "**tamarind** extra",
    "**tamarind",
    "tamarind**",
    "```tamarind```",
    "tamarind\nother",
    "tamarind!",
    "**wrong**",
    "tamarind..",
  ])("rejects incorrect or extra marker text %s", (answer) => {
    expect(matchesWholeAnswer(answer, "tamarind")).toBe(false);
  });

  it.each([
    "1518",
    "15170",
    "1,51,7",
    "15.17",
    "-1517",
    "+1517",
    "1517 or 1518",
    "The answer is 1,517",
  ])("rejects incorrect or extra numeric text %s", (answer) => {
    expect(matchesWholeAnswer(answer, "1517")).toBe(false);
  });
});
