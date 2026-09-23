import { createServiceLogger } from "@gradiated/control";
import { describe, expect, it } from "vitest";

import { WorkerInvariantError } from "../src/errors.js";

describe("worker invariant errors", () => {
  it("reach the service log as a bounded error code without the message", () => {
    const lines: string[] = [];
    const log = createServiceLogger("worker", (line) => lines.push(line));
    const error = new WorkerInvariantError(
      "EMISSING_BILLING_ACCOUNT",
      "Billing account is missing for a chargeable organization",
    );

    log("error", "worker_loop_failed", { loop: "settlement", error });

    expect(lines).toHaveLength(1);
    expect(JSON.parse(lines[0] ?? "")).toMatchObject({
      error_type: "WorkerInvariantError",
      error_code: "EMISSING_BILLING_ACCOUNT",
    });
    expect(lines[0]).not.toContain("Billing account");
  });
});
