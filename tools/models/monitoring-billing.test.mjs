import assert from "node:assert/strict";
import test from "node:test";
import { configureMonitoringBilling } from "./monitoring-billing.mjs";

const workspaceId = "01a0ec7f-68fc-7149-b314-e600ed3d579a";
const account = {
  id: "01a039af-0aae-7459-b9bf-eb346420f6b3",
  name: "Gradiated",
  status: "active",
  mode: "prepaid",
  balance: "-6854",
};
const clientFor = (rows) => ({ query: async () => ({ rows }) });

test("inspection does not post credit and reports the actual balance", async () => {
  const result = await configureMonitoringBilling(clientFor([account]), {
    workspaceId,
    postCredit: () => assert.fail("inspection must not post credit"),
  });
  assert.equal(result.balance, "-6854");
  assert.equal(result.mode, "prepaid");
});

test("posts the fixed reserve through the ledger without changing billing mode", async () => {
  const entries = [];
  const result = await configureMonitoringBilling(clientFor([account]), {
    workspaceId,
    applyCredit: true,
    postCredit: async (entry) => {
      entries.push(entry);
      return { ...entry, id: "transaction", balanceAfter: 9_999_999_993_146n };
    },
  });
  assert.deepEqual(entries, [
    {
      organizationId: account.id,
      type: "credit",
      amount: 10_000_000_000_000n,
      sourceType: "operator",
      sourceId: "gradiated-inference-monitoring-reserve-v1",
      createdBy: null,
    },
  ]);
  assert.equal(result.mode, "prepaid");
  assert.equal(result.creditNanoUsd, "10000000000000");
  assert.equal(result.postedBalanceNanoUsd, "9999999993146");
});

test("refuses other workspaces and account identities before posting", async () => {
  const postCredit = () => assert.fail("identity guard must prevent credit");
  await assert.rejects(
    configureMonitoringBilling(clientFor([account]), {
      workspaceId: "other",
      applyCredit: true,
      postCredit,
    }),
  );
  for (const rows of [
    [],
    [account, account],
    [{ ...account, id: "other" }],
    [{ ...account, name: "Customer" }],
    [{ ...account, status: "suspended" }],
    [{ ...account, mode: "invoiced" }],
  ]) {
    await assert.rejects(
      configureMonitoringBilling(clientFor(rows), {
        workspaceId,
        applyCredit: true,
        postCredit,
      }),
    );
  }
});

test("retries use the same ledger idempotency identity", async () => {
  const entries = [];
  const options = {
    workspaceId,
    applyCredit: true,
    postCredit: async (entry) => {
      entries.push(entry);
      return {
        ...entry,
        id: "same-transaction",
        balanceAfter: 10_000_000_000_000n,
      };
    },
  };
  const first = await configureMonitoringBilling(clientFor([account]), options);
  const second = await configureMonitoringBilling(
    clientFor([account]),
    options,
  );
  assert.equal(first.transactionId, second.transactionId);
  assert.deepEqual(entries[0], entries[1]);
});

test("ledger errors are propagated without another posting attempt", async () => {
  let attempts = 0;
  await assert.rejects(
    configureMonitoringBilling(clientFor([account]), {
      workspaceId,
      applyCredit: true,
      postCredit: async () => {
        attempts++;
        throw new Error("ledger unavailable");
      },
    }),
    /ledger unavailable/,
  );
  assert.equal(attempts, 1);
});
