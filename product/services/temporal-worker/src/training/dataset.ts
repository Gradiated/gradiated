import { SftDatasetManifestSchema } from "@gradiated/contracts";
import type { buildSftDataset, TrainingArtifacts } from "@gradiated/control";

export const persistTrainingDataset = async (
  artifacts: TrainingArtifacts,
  prefix: string,
  dataset: Awaited<ReturnType<typeof buildSftDataset>>,
  inputCutoff: string,
) => {
  const put = (name: string, bytes: Uint8Array) =>
    artifacts.put(`${prefix}/${name}`, bytes, { expiring: true });
  const train = await put("train.jsonl", dataset.files.train);
  const validation = await put("validation.jsonl", dataset.files.validation);
  const test = await put("test.jsonl", dataset.files.test);
  const sampleRows = dataset.files.test
    .toString()
    .trim()
    .split("\n")
    .slice(0, 64);
  const evaluation = await put(
    "evaluation.jsonl",
    Buffer.from(sampleRows.join("\n") + "\n"),
  );
  const split = (examples: number, file: typeof train) => ({
    examples,
    files: [
      {
        uri: artifacts.uri(file.key),
        sha256: file.sha256,
        size_bytes: file.size_bytes,
      },
    ],
  });
  const { oldest_trace_at, newest_trace_at } = dataset.summary;
  const manifest = SftDatasetManifestSchema.parse({
    schema_version: 1,
    format: "conversational_prompt_completion",
    encoding: "jsonl",
    splits: {
      train: split(dataset.summary.train, train),
      validation: split(dataset.summary.validation, validation),
      test: split(dataset.summary.test, test),
    },
    evaluation_sample: {
      ...split(sampleRows.length, evaluation),
      source_split: "test",
      selection: "first_by_example_id",
      max_examples: 64,
    },
    builder: dataset.builder,
    ...(oldest_trace_at && newest_trace_at
      ? {
          provenance: {
            input_cutoff: inputCutoff,
            oldest_trace_at,
            newest_trace_at,
          },
        }
      : {}),
  });
  await put("dataset-manifest.json", Buffer.from(JSON.stringify(manifest)));

  return {
    train,
    validation,
    evaluation,
    summary: { ...dataset.summary, evaluation_examples: sampleRows.length },
  };
};
