import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { waitlistSignups } from "../src/db/schema/index.js";
import {
  createWaitlistService,
  type WaitlistService,
} from "../src/waitlist/service.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("waitlist", () => {
  let testDatabase: TestDatabase;
  let waitlist: WaitlistService;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
    waitlist = createWaitlistService(testDatabase.database);
  });

  afterAll(() => testDatabase.dispose());

  it("creates a signup once and updates the answers on a later join", async () => {
    const first = await waitlist.join({
      email: "ada@example.test",
      companySize: "1-10",
      monthlyTokenSpendUsd: "100",
      motivation: "Cheaper inference.",
    });
    const second = await waitlist.join({
      email: "  ADA@Example.test ",
      companySize: "11-50",
      monthlyTokenSpendUsd: "1000",
      motivation: "Faster inference.",
    });

    const rows = await testDatabase.database
      .select()
      .from(waitlistSignups)
      .where(eq(waitlistSignups.email, "ada@example.test"));

    expect(first).toEqual({ created: true, email: "ada@example.test" });
    expect(second).toEqual({ created: false, email: "ada@example.test" });
    expect(rows).toMatchObject([
      {
        companySize: "11-50",
        monthlyTokenSpendUsd: "1000",
        motivation: "Faster inference.",
      },
    ]);
  });
});
