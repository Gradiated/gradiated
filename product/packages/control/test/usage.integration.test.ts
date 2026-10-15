import type { ClickHouseClient } from "@clickhouse/client";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import { ControlServiceError } from "../src/errors.js";
import { decodeCursor } from "../src/usage/query.js";
import { createUsageService } from "../src/usage/service.js";
import { seedMember, seedUser } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { generation, range } from "./support/usage.js";

describe("usage service", () => {
  let testDatabase: TestDatabase;
  let userId: string;
  let organizationId: string;
  let workspaceId: string;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
    ({ userId, organizationId, workspaceId } = await seedMember(
      testDatabase.database,
      { role: "member" },
    ));
  });

  afterAll(() => testDatabase.dispose());

  const fakeClickHouse = (
    reply: (query: string) => Promise<unknown[]> | unknown[],
  ) => {
    const query = vi.fn(async (params: { query: string }) => {
      const rows = await reply(params.query);

      return { json: async () => rows };
    });

    return {
      query,
      client: { query } as unknown as ClickHouseClient,
    };
  };

  const listPage = (
    client: ClickHouseClient,
    overrides: { cursor?: string; userId?: string } = {},
  ) =>
    createUsageService(testDatabase.database, client).listGenerations({
      userId,
      workspaceId,
      range,
      limit: 2,
      sort: "newest",
      ...overrides,
    });

  it("returns a next cursor only when another page exists", async () => {
    const rows = [
      generation("3", "2026-08-15T12:00:03.000000Z"),
      generation("2", "2026-08-15T12:00:02.000000Z"),
      generation("1", "2026-08-15T12:00:01.000000Z"),
    ];
    const clickhouse = fakeClickHouse(() => rows);

    const first = await listPage(clickhouse.client);
    const last = await listPage(fakeClickHouse(() => rows.slice(2)).client);

    expect(first.data.map((row) => row.id)).toEqual(
      rows.slice(0, 2).map((row) => row.id),
    );
    expect(decodeCursor(first.nextCursor ?? "", "newest")).toMatchObject({
      id: rows[1]?.id,
    });
    expect(clickhouse.query.mock.calls[0]?.[0]).toMatchObject({
      query_params: { limit: 3 },
    });
    expect(last.nextCursor).toBeNull();
  });

  it("rejects an invalid cursor before querying ClickHouse", async () => {
    const clickhouse = fakeClickHouse(() => []);

    await expect(
      listPage(clickhouse.client, { cursor: "garbage" }),
    ).rejects.toMatchObject({ code: "not_found" });

    expect(clickhouse.query).not.toHaveBeenCalled();
  });

  it("hides the workspace from a non-member without querying ClickHouse", async () => {
    const clickhouse = fakeClickHouse(() => []);
    const outsider = await seedUser(testDatabase.database);

    await expect(
      listPage(clickhouse.client, { userId: outsider }),
    ).rejects.toMatchObject({ code: "not_found" });

    expect(clickhouse.query).not.toHaveBeenCalled();
  });

  it.each([
    ["a distribution channel", { kind: "distribution_channel" as const }, {}],
    ["an archived workspace", {}, { archived: true }],
  ])(
    "hides %s without querying ClickHouse",
    async (_name, organization, workspace) => {
      const clickhouse = fakeClickHouse(() => []);
      const hidden = await seedMember(testDatabase.database, {
        role: "admin",
        organization,
        workspace,
      });

      await expect(
        createUsageService(
          testDatabase.database,
          clickhouse.client,
        ).listGenerations({
          ...hidden,
          range,
          limit: 2,
          sort: "newest",
        }),
      ).rejects.toMatchObject({ code: "not_found" });

      expect(clickhouse.query).not.toHaveBeenCalled();
    },
  );

  it.each([
    ["a ClickHouse rejection", new Error("connection refused")],
    ["a malformed row", undefined],
  ])("reports %s as unavailable with its cause", async (_name, failure) => {
    const clickhouse = fakeClickHouse(() => {
      if (failure) throw failure;
      return [{ id: "not-a-generation" }];
    });

    const page = listPage(clickhouse.client);

    await expect(page).rejects.toBeInstanceOf(ControlServiceError);
    await expect(page).rejects.toMatchObject({
      code: "unavailable",
      cause: failure ?? expect.any(Error),
    });
  });

  it("summarizes the single total row with the daily and model rows", async () => {
    const totals = {
      charge: "30",
      input_tokens: "10",
      output_tokens: "20",
      generation_count: "3",
      succeeded_count: "2",
    };
    const daily = [
      {
        date: "2026-08-15",
        charge: "30",
        input_tokens: "10",
        output_tokens: "20",
        generation_count: "3",
      },
    ];
    const models = [
      {
        model_id: "vendor/model",
        charge: "30",
        input_tokens: "10",
        output_tokens: "20",
        generation_count: "3",
      },
    ];
    const clickhouse = fakeClickHouse((query) => {
      if (query.includes("GROUP BY date")) return daily;
      if (query.includes("GROUP BY model_id")) return models;
      return [totals];
    });

    const summary = await createUsageService(
      testDatabase.database,
      clickhouse.client,
    ).getSummary({ userId, workspaceId, range });

    expect(summary).toEqual({
      charge: "30",
      inputTokens: "10",
      outputTokens: "20",
      generationCount: "3",
      succeededCount: "2",
      daily,
      models,
    });
  });

  it("reports a total without exactly one row as unavailable", async () => {
    const clickhouse = fakeClickHouse(() => []);

    await expect(
      createUsageService(testDatabase.database, clickhouse.client).getSummary({
        userId,
        workspaceId,
        range,
      }),
    ).rejects.toMatchObject({ code: "unavailable" });
  });
});
