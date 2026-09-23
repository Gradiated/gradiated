import { describe, expect, it } from "vitest";

import {
  clickHouseServerEnvironmentSchema,
  clickHouseUrl,
} from "../src/clickhouse/client.js";
import {
  pendingMigrations,
  safeIdentifier,
  selectMigrationFiles,
  type Migration,
} from "../src/clickhouse/migrations.js";

const migration = (name: string, checksum = `${name}-checksum`): Migration => ({
  checksum,
  name,
  query: `-- ${name}`,
});

describe("ClickHouse migration planning", () => {
  it("chooses only numbered SQL files in order", () => {
    expect(
      selectMigrationFiles([
        "0002_profiling_events.sql",
        "README.md",
        "0001_generations.sql",
        "1_short.sql",
        "0003_Upper.sql",
        "0004_draft.sql.bak",
      ]),
    ).toEqual(["0001_generations.sql", "0002_profiling_events.sql"]);
  });

  it("skips applied migrations and keeps the pending ones in order", () => {
    const files = [migration("0001_a.sql"), migration("0002_b.sql")];

    expect(
      pendingMigrations(
        files,
        new Map([["0001_a.sql", "0001_a.sql-checksum"]]),
      ),
    ).toEqual([files[1]]);
  });

  it("refuses to continue when an applied migration changed", () => {
    const files = [migration("0001_a.sql"), migration("0002_b.sql")];

    expect(() =>
      pendingMigrations(files, new Map([["0001_a.sql", "other-checksum"]])),
    ).toThrow("Applied migration changed: 0001_a.sql");
  });
});

describe("ClickHouse identifiers and URLs", () => {
  it("quotes a valid identifier", () => {
    expect(safeIdentifier("CLICKHOUSE_DATABASE", "gradiated_1")).toBe(
      "`gradiated_1`",
    );
  });

  it.each(["with`tick", "with space", "1leading_digit", ""])(
    "rejects %j",
    (value) => {
      expect(() => safeIdentifier("CLICKHOUSE_DATABASE", value)).toThrow(
        "CLICKHOUSE_DATABASE must be a ClickHouse identifier",
      );
    },
  );

  it("builds the server URL from the scheme, host and port", () => {
    const url = (port: string, secure: string) =>
      clickHouseUrl(
        clickHouseServerEnvironmentSchema.parse({
          CLICKHOUSE_HOST: "db",
          CLICKHOUSE_PORT: port,
          CLICKHOUSE_SECURE: secure,
        }),
      );

    expect(url("8443", "true")).toBe("https://db:8443");
    expect(url("8123", "false")).toBe("http://db:8123");
  });

  it.each([
    ["0", "true"],
    ["65536", "true"],
    ["8123", "yes"],
  ])("rejects port %s with secure %s", (port, secure) => {
    expect(() =>
      clickHouseServerEnvironmentSchema.parse({
        CLICKHOUSE_HOST: "db",
        CLICKHOUSE_PORT: port,
        CLICKHOUSE_SECURE: secure,
      }),
    ).toThrow();
  });
});
