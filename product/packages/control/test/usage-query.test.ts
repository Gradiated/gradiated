import { randomUUID } from "node:crypto";

import { describe, expect, it } from "vitest";

import {
  decodeCursor,
  encodeCursor,
  generationFilter,
  type GenerationFilters,
} from "../src/usage/query.js";
import { generation, range } from "./support/usage.js";

const filters = (
  overrides: Partial<GenerationFilters> = {},
): GenerationFilters => ({
  organizationId: randomUUID(),
  workspaceId: randomUUID(),
  range,
  sort: "newest",
  ...overrides,
});

const encoded = (value: unknown) =>
  Buffer.from(JSON.stringify(value), "utf8").toString("base64url");

describe("usage cursor", () => {
  const row = generation("250", "2026-08-15T12:00:00.000000Z");

  it.each(["newest", "highest_cost"] as const)(
    "round-trips a %s cursor",
    (sort) => {
      expect(decodeCursor(encodeCursor(row, sort), sort)).toEqual({
        ...(sort === "highest_cost" ? { charge: "250" } : {}),
        completedAt: row.completed_at,
        id: row.id,
        sort,
      });
    },
  );

  it("preserves exact charge and timestamp precision in a client-supplied cursor", () => {
    const cursor = {
      sort: "highest_cost" as const,
      charge: "18446744073709551615",
      completedAt: "2026-08-15T12:00:00.123456Z",
      id: row.id,
    };
    expect(decodeCursor(encoded(cursor), "highest_cost")).toEqual(cursor);
  });

  it.each([
    [
      "a numeric charge that has already lost precision",
      { charge: 9_007_199_254_740_992 },
    ],
    ["a signed charge", { charge: "-1" }],
    ["a fractional charge", { charge: "1.5" }],
    ["an invalid timestamp", { completedAt: "not-a-timestamp" }],
    ["an invalid generation ID", { id: "not-a-uuid" }],
  ] as const)("rejects a client cursor with %s", (_name, overrides) => {
    const cursor = encoded({
      sort: "highest_cost",
      charge: "250",
      completedAt: row.completed_at,
      id: row.id,
      ...overrides,
    });
    expect(() => decodeCursor(cursor, "highest_cost")).toThrow(
      expect.objectContaining({ code: "not_found" }),
    );
  });

  it.each([
    ["a cursor for another sort", encodeCursor(row, "newest"), "highest_cost"],
    ["a cursor that is not JSON", "not-a-cursor", "newest"],
    [
      "a highest_cost cursor without a charge",
      encoded({
        completedAt: row.completed_at,
        id: row.id,
        sort: "highest_cost",
      }),
      "highest_cost",
    ],
  ] as const)("rejects %s", (_name, cursor, sort) => {
    expect(() => decodeCursor(cursor, sort)).toThrow(
      expect.objectContaining({
        code: "not_found",
        message: "The page cursor is invalid.",
      }),
    );
  });
});

describe("generation filter", () => {
  it("limits every query to the workspace and the range", () => {
    const input = filters();

    expect(generationFilter(input, undefined)).toEqual({
      where: [
        "g.organization_id = {organization_id:UUID}",
        "g.workspace_id = {workspace_id:UUID}",
        "g.completed_at >= {from:DateTime64(6, 'UTC')}",
        "g.completed_at < {to:DateTime64(6, 'UTC')}",
      ],
      params: {
        organization_id: input.organizationId,
        workspace_id: input.workspaceId,
        from: "2026-08-01 00:00:00.000",
        to: "2026-09-01 00:00:00.000",
      },
    });
  });

  it.each([
    ["apiKeyId", randomUUID(), "api_key_id", "{api_key_id:UUID}"],
    ["model", "vendor/model", "model", "{model:String}"],
    ["search", "abc", "search", "{search:String}"],
    ["status", "failed", "status", "{status:String}"],
  ] as const)(
    "adds only the %s clause and its parameter",
    (field, value, param, placeholder) => {
      const base = generationFilter(filters(), undefined);
      const filtered = generationFilter(filters({ [field]: value }), undefined);

      expect(filtered.where).toHaveLength(base.where.length + 1);
      expect(filtered.where.at(-1)).toContain(placeholder);
      expect(filtered.params[param]).toBe(value);
      expect(Object.keys(filtered.params)).toHaveLength(
        Object.keys(base.params).length + 1,
      );
    },
  );

  it("adds the cursor position for each sort", () => {
    const id = randomUUID();
    const completedAt = "2026-08-15T12:00:00.000000Z";

    const newest = generationFilter(filters(), {
      completedAt,
      id,
      sort: "newest",
    });
    const highestCost = generationFilter(filters(), {
      charge: "250",
      completedAt,
      id,
      sort: "highest_cost",
    });

    expect(newest.params).toMatchObject({
      cursor_id: id,
      cursor_time: "2026-08-15 12:00:00.000",
    });
    expect(newest.params).not.toHaveProperty("cursor_charge");
    expect(highestCost.params).toMatchObject({ cursor_charge: "250" });
    expect(highestCost.where.at(-1)).toContain("g.charge <");
  });
});
