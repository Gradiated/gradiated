import { laterComparisons } from "./laterComparisons";
import article from "../script.md?cited-article";
import { openingSceneKeys } from "./opening";
import { applicationScenes } from "./ApplicationEnvironments";
import { architectureScenes } from "./ArchitectureTour";
import { networkIntroScenes } from "./NetworkIntro";
import { configurationScenes } from "./ChipContinuation";

export const measurementScenes = [
  "measuring-inference",
  "measure-autonomous",
  "measure-skip",
  "measure-multiply",
  "measure-divide",
  "measure-score-pipeline",
  "measure-two-lanes",
  "measure-four-lanes",
  "measure-eight-lanes",
  "measure-feedforward-divide",
  "measure-down-pipeline",
  "measure-cache-pipeline",
  "measure-attention-divide",
  "measure-lutram",
  "measure-exp-pair",
] as const;

export const measurementStepFor = (scene: string) =>
  measurementScenes.findIndex((key) => key === scene);

export const groups = [
  [
    ...openingSceneKeys,
    ...applicationScenes,
    ...architectureScenes,
    ...configurationScenes,
  ],
  ["clock-network"],
  [
    "resources-map",
    "block-ram",
    "arithmetic-map",
    "arithmetic-blocks",
    "arithmetic-accumulate",
    "arithmetic-save",
    "arithmetic-next",
    "resource-columns",
    ...networkIntroScenes,
    "neuron-hardware",
    "neuron",
    "neuron-next",
  ],
  ["pins", "memory-roles", "our-board", "board-request"],
  ["transformer-cache-map", "transformer-cache", "token-journey"],
  ["chip-choices"],
  [...measurementScenes, ...Object.keys(laterComparisons)],
] as const;

export const figureTitles = [
  "Inside the same FPGA",
  "Leave time for signals to settle",
  "Logic, memory and arithmetic",
  "Signals and settings have different paths",
  "From a token to the next token",
  "Different ways to organise a calculation",
  "Measuring inference on the KV260",
];

export const scenes = article.scenes.map((scene) => {
  const group = groups.findIndex((keys) =>
    (keys as readonly string[]).includes(scene.key),
  );

  if (group < 0) throw new Error(`Missing FPGA figure for ${scene.key}`);

  return { ...scene, group };
});

if (
  scenes.length !== groups.flat().length ||
  new Set(groups.flat()).size !== groups.flat().length ||
  new Set(scenes.map((scene) => scene.key)).size !== scenes.length
) {
  throw new Error("FPGA prose and figure sequence do not match");
}

export const chapters = scenes.flatMap((scene, index) => {
  const heading = scene.html.match(/<h2[^>]*>(.*?)<\/h2>/s);

  return heading
    ? [
        {
          id: `fpga-${scene.key}`,
          label: heading[1].replace(/<[^>]+>/g, ""),
          index,
        },
      ]
    : [];
});

export const { introduction, bibliography } = article;
