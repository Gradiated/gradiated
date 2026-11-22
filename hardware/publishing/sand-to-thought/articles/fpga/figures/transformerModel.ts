import data from "./data/tiny-transformer.json";
import requestData from "./data/tiny-text-request.json";

export const transformerExample = data;

export const roundToEven = (value: number, shift: number) => {
  const divisor = 2 ** shift;
  const magnitude = Math.abs(value);
  const whole = Math.floor(magnitude / divisor);
  const remainder = magnitude % divisor;
  const increment =
    remainder > divisor / 2 || (remainder === divisor / 2 && whole % 2 === 1);

  return Math.sign(value) * (whole + Number(increment));
};

export const projectionSnapshot = (row: number, step: number) => {
  const recorded = data.projection.rows[row];

  if (!recorded || !Number.isInteger(step) || step < 0 || step > 33) {
    throw new Error("Projection excerpt has two rows and 34 inspection states");
  }

  const count = Math.min(32, step);
  const coordinate = Math.max(0, count - 1);

  return {
    count,
    coordinate,
    input: data.projection.inputs[coordinate],
    weight: recorded.weights[coordinate],
    product: recorded.products[coordinate],
    sum: count ? recorded.sums[count - 1] : 0,
    cycle:
      step === 33
        ? recorded.resultCycle
        : count
          ? recorded.cycles[count - 1]
          : null,
    output: step === 33 ? recorded.result : null,
  };
};

export type CacheMode = "writes" | "full" | "reset";

export const cacheSnapshot = (
  mode: CacheMode,
  frameIndex: number,
  position: number,
  coordinate: number,
) => {
  const { cache } = data;

  if (
    !Number.isInteger(position) ||
    position < 0 ||
    position >= cache.positions ||
    !Number.isInteger(coordinate) ||
    coordinate < 0 ||
    coordinate >= cache.coordinates ||
    !Number.isInteger(frameIndex) ||
    frameIndex < 0 ||
    frameIndex >= cache.frames.length
  ) {
    throw new Error("Cache selection is outside the recorded excerpt");
  }

  const frame = cache.frames[frameIndex];
  const count = mode === "full" ? 256 : mode === "reset" ? 0 : frame.count;
  const partial = mode === "writes" ? frame.partial : 0;
  const address = position * 32 + coordinate;
  let pair: number[] | undefined;

  if (mode === "writes") {
    for (const event of cache.frames.slice(0, frameIndex + 1)) {
      if (event.write?.[0] === position && event.write[1] === coordinate) {
        pair = event.write.slice(2);
      }
    }
  } else {
    pair = cache.fullReadback[address];
  }

  return {
    count,
    partial,
    address,
    pair,
    readable: position < count,
    cycle:
      mode === "full"
        ? cache.fullCycle
        : mode === "reset"
          ? cache.resetReadRejectedCycle
          : frame.cycle,
  };
};

export const nextCacheCommit = (frameIndex: number) => {
  const { frames } = data.cache;
  const next = frames.findIndex(
    (frame, index) =>
      index > frameIndex && frame.count > frames[frameIndex].count,
  );

  return next < 0 ? frames.length - 1 : next;
};

export const textRequest = requestData;

export const encodeRequest = (text: string) => {
  const bytes = new TextEncoder().encode(text);
  if (bytes.length > 48) throw new Error("Input exceeds 48 UTF-8 bytes");

  return [
    256,
    ...Array.from(bytes).flatMap((byte) => [
      272 + (byte >> 4),
      288 + (byte & 15),
    ]),
  ];
};

export const requestStages = [
  {
    label: "Supply a",
    description: "The CPU encodes the input a.",
  },
  {
    label: "Process supplied input",
    description:
      "The first two tokens fill the cache. Follow token 289 at position 2.",
  },
  {
    label: "Token → working numbers",
    description: "Token 289 selects its 32 learned embedding values.",
  },
  {
    label: "Prepare comparisons and content",
    description: "Multiply and add to produce the query, key and value.",
  },
  {
    label: "Include position",
    description: "Apply the position adjustment to Q and K.",
  },
  {
    label: "Combine earlier information",
    description:
      "Save K and V. Compare Q with the cached keys to decide how to combine their values.",
  },
  {
    label: "Transform and add back",
    description:
      "Transform the attention result and add the earlier working values back in.",
  },
  {
    label: "Further transformation",
    description:
      "The gated layer goes from 32 to 128 numbers and back, then adds the earlier values.",
  },
  {
    label: "Score the next token",
    description: "More prominent squares indicate higher scores.",
  },
  {
    label: "The CPU chooses R",
    description: "The CPU chooses token 82 and appends R.",
  },
  {
    label: "Feed R back",
    description:
      "Feed R back as the fourth token and keep the existing cache entries.",
  },
  {
    label: "Score after R",
    description: "Processing R adds a cache entry and produces new scores.",
  },
  {
    label: "The CPU chooses e",
    description: "The CPU chooses token 101 and appends e.",
  },
  {
    label: "Repeat to grow the output",
    description:
      "Feed e back to continue. Stop at the end token or length limit.",
  },
] as const;

export const requestSnapshot = (stage: number) => {
  if (!Number.isInteger(stage) || stage < 0 || stage >= requestStages.length) {
    throw new Error("Unknown request stage");
  }

  const prediction = requestData.predictions[stage >= 10 ? 1 : 0];
  const names = [
    "embed",
    "embed",
    "embed",
    "q",
    "qrot",
    "context",
    "res1",
    "res2",
    "normfinal",
    "normfinal",
    "embed",
    "normfinal",
    "normfinal",
  ] as const;
  const name = names[stage];
  const vector = name ? prediction.vectors[name] : undefined;
  const candidates = prediction.scores
    .map((score, token) => ({ token, score }))
    .sort((a, b) => b.score - a.score || a.token - b.token)
    .slice(0, 5);

  return {
    cacheCount: stage === 0 ? 0 : stage < 5 ? 2 : stage < 11 ? 3 : 4,
    winner: prediction.winner,
    vector,
    scores: prediction.scores,
    candidates,
    output: stage < 9 ? "" : stage < 12 ? "R" : "Re",
  };
};

export const requestProjectionSnapshot = (row: number, step: number) => {
  const recorded = requestData.projection.rows[row];
  if (!recorded || !Number.isInteger(step) || step < 0 || step > 97) {
    throw new Error("Projection has two rows and 98 teaching states");
  }

  const coordinate = Math.min(31, Math.max(0, Math.floor((step - 1) / 3)));
  const phase =
    step === 0
      ? "ready"
      : step === 97
        ? "output"
        : ["read", "multiply", "save"][(step - 1) % 3];
  const count = Math.min(32, Math.floor(step / 3));

  return {
    coordinate,
    phase,
    count,
    input: requestData.projection.inputs[coordinate],
    weight: recorded.weights[coordinate],
    product:
      phase === "multiply" || phase === "save"
        ? recorded.products[coordinate]
        : null,
    sum: count ? recorded.sums[count - 1] : 0,
    output: step === 97 ? recorded.result : null,
  };
};
