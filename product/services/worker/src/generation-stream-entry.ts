import {
  GenerationSettledSchema,
  type GenerationSettled,
} from "@gradiated/contracts";
import { storedGenerationPropertiesSchema } from "@gradiated/control";
import type { z } from "zod";

import { WorkerInvariantError } from "./errors.js";
import { slotContaining } from "./settlement-slot.js";
import { parseStreamId } from "./stream-id.js";

export type StreamMessage = {
  id: string;
  message: Record<string, string>;
};

export type GenerationStreamEntry = {
  event: GenerationSettled;
  slotId: string;
};

const readFields = ({ id, message }: StreamMessage) => {
  const fields = Object.keys(message).sort();
  const { generation_id: generationId, properties } = message;

  if (
    fields.length !== 2 ||
    fields[0] !== "generation_id" ||
    fields[1] !== "properties" ||
    !generationId ||
    !properties
  ) {
    throw new WorkerInvariantError(
      "EINVALID_STREAM_ENTRY",
      `Invalid generation stream fields at ${id}`,
    );
  }

  return { generationId, properties };
};

const parseJson = (id: string, serialized: string): unknown => {
  try {
    return JSON.parse(serialized);
  } catch (error) {
    throw new WorkerInvariantError(
      "EINVALID_GENERATION_JSON",
      `Invalid generation properties JSON at ${id}`,
      { cause: error },
    );
  }
};

const requireValid = <T>(id: string, result: z.ZodSafeParseResult<T>): T => {
  if (!result.success) {
    throw new WorkerInvariantError(
      "EINVALID_GENERATION_EVENT",
      `Invalid generation event at ${id}`,
      { cause: result.error },
    );
  }

  return result.data;
};

export const parseGenerationStreamEntry = (
  entry: StreamMessage,
): GenerationStreamEntry => {
  const { generationId, properties } = readFields(entry);
  const slotId = slotContaining(parseStreamId(entry.id).milliseconds).id;

  const event = requireValid(
    entry.id,
    GenerationSettledSchema.safeParse({
      generation_id: generationId,
      properties: parseJson(entry.id, properties),
    }),
  );

  requireValid(
    entry.id,
    storedGenerationPropertiesSchema.safeParse({
      ...event.properties,
      settlement: { slot_id: slotId },
    }),
  );

  return { event, slotId };
};
