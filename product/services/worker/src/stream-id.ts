import { WorkerInvariantError } from "./errors.js";

export type StreamId = { milliseconds: number; sequence: bigint };

const streamIdPattern = /^(0|[1-9][0-9]*)-(0|[1-9][0-9]*)$/;

export const parseStreamId = (id: string): StreamId => {
  const match = streamIdPattern.exec(id);
  const milliseconds = Number(match?.[1]);

  if (!match?.[2] || !Number.isSafeInteger(milliseconds)) {
    throw new WorkerInvariantError(
      "EINVALID_STREAM_ID",
      `Invalid Valkey Stream ID: ${id}`,
    );
  }

  return { milliseconds, sequence: BigInt(match[2]) };
};

export const formatStreamId = ({ milliseconds, sequence }: StreamId): string =>
  `${milliseconds}-${sequence}`;

const maxSequence = 2n ** 64n - 1n;

export const nextStreamId = ({ milliseconds, sequence }: StreamId): StreamId =>
  sequence === maxSequence
    ? { milliseconds: milliseconds + 1, sequence: 0n }
    : { milliseconds, sequence: sequence + 1n };
