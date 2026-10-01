import { createHash } from "node:crypto";
import { z } from "zod";
import type { RunDatasetSummary, SftExampleSchema } from "@gradiated/contracts";
import { readTraceRecord, type TraceManifestRow } from "../traces/content.js";
import type { ContentStore } from "../traces/storage.js";
import { trainingTraceRows } from "./traces.js";
import type { TrainingInput } from "./types.js";

const TextMessageSchema = z
  .object({
    role: z.enum(["system", "user", "assistant"]),
    content: z.string().min(1).max(32_000),
  })
  .strict();

const TextTraceSchema = z.object({
  version: z.literal(1),
  messages: z.array(TextMessageSchema).min(1).max(100),
  tools: z.array(z.unknown()).max(0).default([]),
  output: z.object({
    role: z.literal("assistant"),
    content: z.string().min(1).max(32_000),
    tool_calls: z.array(z.unknown()).max(0).default([]),
  }),
});

export const sha256 = (value: string | Uint8Array) =>
  createHash("sha256").update(value).digest("hex");

export type SftExample = z.infer<typeof SftExampleSchema> & {
  id: string;
  group: string;
};
export type DatasetSplit = "train" | "validation" | "test";

const DATASET_BUILDER = {
  id: "gradiated-traces-sft",
  version: 1,
  split: {
    algorithm: "sha256_group_modulo_10",
    group_by: "session_and_shared_prompt",
    buckets: { train: [2, 3, 4, 5, 6, 7, 8, 9], validation: [1], test: [0] },
  },
  max_examples: 10_000,
  max_content_bytes: 64 * 1024 * 1024,
} as const;

type CollectedExample = SftExample & { at: string; sizeBytes: number };

const createExampleGroups = () => {
  const parents = new Map<string, string>();
  const find = (group: string) => {
    const path: string[] = [];
    let parent = parents.get(group);

    while (parent !== undefined) {
      path.push(group);
      group = parent;
      parent = parents.get(group);
    }

    for (const member of path) parents.set(member, group);

    return group;
  };
  const merge = (group: string, related: string) => {
    const from = find(group);
    const to = find(related);

    if (from !== to) parents.set(from, to);
  };

  return { find, merge };
};

const readSftExample = async (
  store: ContentStore,
  key: string,
  row: TraceManifestRow,
): Promise<CollectedExample | null> => {
  if (
    !row.trainable ||
    row.source === "relay" ||
    row.outcome !== "complete" ||
    row.status !== 200
  )
    return null;

  const record = await readTraceRecord(store, key, row);
  const parsed = TextTraceSchema.safeParse(record.canonical);
  if (!parsed.success || parsed.data.messages.at(-1)?.role !== "user")
    return null;

  const { messages, output } = parsed.data;
  if (!output.content.trim()) return null;

  const content = {
    prompt: messages,
    completion: [{ role: "assistant" as const, content: output.content }],
  };
  const encoded = JSON.stringify(content);

  return {
    id: sha256(encoded),
    group: row.trace_id ?? row.generation_id,
    ...content,
    at: row.started_at,
    sizeBytes: Buffer.byteLength(encoded),
  };
};

const collectExamples = async (store: ContentStore, input: TrainingInput) => {
  const examples = new Map<string, CollectedExample>();
  const groups = createExampleGroups();
  let eligibleExamples = 0;
  let bytes = 0;

  for await (const { key, row } of trainingTraceRows(store, {
    workspaceId: input.workspaceId,
    task: input.name,
    since: null,
    cutoff: new Date(input.inputCutoff),
  })) {
    const example = await readSftExample(store, key, row);
    if (!example) continue;

    const duplicate = examples.get(example.id);
    if (duplicate) {
      groups.merge(example.group, duplicate.group);
    } else {
      if (bytes + example.sizeBytes > DATASET_BUILDER.max_content_bytes) break;

      bytes += example.sizeBytes;
      examples.set(example.id, example);
    }

    eligibleExamples++;
    if (examples.size === DATASET_BUILDER.max_examples) break;
  }

  return { examples: [...examples.values()], groups, eligibleExamples };
};

const mergeSharedPrompts = (
  examples: CollectedExample[],
  groups: ReturnType<typeof createExampleGroups>,
) => {
  const prompts = new Map<string, string>();

  for (const example of examples) {
    const prompt = sha256(JSON.stringify(example.prompt));
    const previous = prompts.get(prompt);
    if (previous !== undefined) groups.merge(example.group, previous);
    else prompts.set(prompt, example.group);
  }
};

const splitExamples = (
  examples: CollectedExample[],
  groups: ReturnType<typeof createExampleGroups>,
) => {
  const splits: Record<DatasetSplit, SftExample[]> = {
    train: [],
    validation: [],
    test: [],
  };

  for (const example of examples) {
    const group = groups.find(example.group);
    const bucket = Number.parseInt(sha256(group).slice(0, 8), 16) % 10;
    const split = bucket === 0 ? "test" : bucket === 1 ? "validation" : "train";
    splits[split].push({
      id: example.id,
      group,
      prompt: example.prompt,
      completion: example.completion,
    });
  }

  if (
    splits.train.length < 10 ||
    !splits.validation.length ||
    !splits.test.length
  )
    throw new Error(
      "SFT needs at least ten training examples and separate validation and test groups.",
    );

  return splits;
};

const encodeJsonl = (rows: SftExample[]) =>
  Buffer.from(
    [...rows]
      .sort((a, b) => a.id.localeCompare(b.id))
      .map((row) => JSON.stringify(row))
      .join("\n") + "\n",
  );

export const buildSftDataset = async (
  store: ContentStore,
  input: TrainingInput,
) => {
  const { examples, groups, eligibleExamples } = await collectExamples(
    store,
    input,
  );
  mergeSharedPrompts(examples, groups);
  const splits = splitExamples(examples, groups);

  const files = {
    train: encodeJsonl(splits.train),
    validation: encodeJsonl(splits.validation),
    test: encodeJsonl(splits.test),
  };
  const times = examples.map((example) => example.at).sort();
  const summary: RunDatasetSummary = {
    oldest_trace_at: times[0]!,
    newest_trace_at: times.at(-1)!,
    eligible_examples: eligibleExamples,
    duplicates_removed: eligibleExamples - examples.length,
    train: splits.train.length,
    validation: splits.validation.length,
    test: splits.test.length,
  };

  return { files, summary, builder: DATASET_BUILDER };
};
