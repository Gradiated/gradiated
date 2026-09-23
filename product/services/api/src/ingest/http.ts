import { timingSafeEqual } from "node:crypto";

import type { Context, ErrorHandler } from "hono";
import { bodyLimit } from "hono/body-limit";

import { serviceLog } from "../logging.js";

const BEARER_PREFIX = "Bearer ";

export const bearerToken = (
  authorization: string | undefined,
): string | undefined =>
  authorization?.startsWith(BEARER_PREFIX)
    ? authorization.slice(BEARER_PREFIX.length)
    : undefined;

export const tokenMatches = (supplied: string, expected: string): boolean => {
  const suppliedBytes = Buffer.from(supplied);
  const expectedBytes = Buffer.from(expected);

  return (
    suppliedBytes.length === expectedBytes.length &&
    timingSafeEqual(suppliedBytes, expectedBytes)
  );
};

export const readJsonBody = async (
  context: Context,
): Promise<{ ok: true; value: unknown } | { ok: false }> => {
  try {
    return { ok: true, value: await context.req.json() };
  } catch {
    return { ok: false };
  }
};

export const ingestBodyLimit = (maxSize: number) =>
  bodyLimit({
    maxSize,
    onError: (context) => context.json({ error: "payload_too_large" }, 413),
  });

export const handleIngestError: ErrorHandler = (error, context) => {
  serviceLog("error", "ingest_failed", {
    error,
    route: context.req.routePath,
  });

  return context.json({ error: "internal_error" }, 500);
};
