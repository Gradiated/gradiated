import type {
  ServingProjector,
  ServingProjectionSnapshot,
  ServingReconciliationReader,
} from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";
import {
  reconcileServingStatePass,
  runServingReconciliationLoop,
} from "../src/serving-reconciliation-loop.js";

const firstTransaction = {
  amount: 100n,
  createdAt: new Date("2026-08-19T12:00:00.000Z"),
  id: "0198ad73-a200-7000-8000-000000000010",
  organizationId: "0198ad73-a200-7000-8000-000000000002",
};
const secondTransaction = {
  amount: -20n,
  createdAt: new Date("2026-08-19T12:01:00.000Z"),
  id: "0198ad73-a200-7000-8000-000000000011",
  organizationId: "0198ad73-a200-7000-8000-000000000002",
};
const thirdTransaction = {
  amount: 50n,
  createdAt: new Date("2026-08-19T12:02:00.000Z"),
  id: "0198ad73-a200-7000-8000-000000000012",
  organizationId: "0198ad73-a200-7000-8000-000000000003",
};

const snapshot: ServingProjectionSnapshot = {
  accounts: [
    {
      balance: 100n,
      billingMode: "prepaid",
      organizationId: firstTransaction.organizationId,
      organizationKind: "customer",
      organizationStatus: "active",
    },
  ],
  credentials: [
    {
      digestHex: "ab".repeat(32),
      credential: {
        apiKeyId: "0198ad73-a200-7000-8000-000000000020",
        expiresAt: null,
        organizationId: firstTransaction.organizationId,
        revokedAt: null,
        workspaceId: "0198ad73-a200-7000-8000-000000000021",
      },
    },
  ],
  models: [
    {
      deployments: [],
      id: "moonshotai/kimi-k3",
      name: "Kimi K3",
      properties: {} as never,
      status: "available",
    },
  ],
  workspaces: [
    {
      archivedAt: null,
      createdAt: new Date("2026-08-19T12:00:00.000Z"),
      id: "0198ad73-a200-7000-8000-000000000021",
      isDefault: true,
      name: "Default",
      organizationId: firstTransaction.organizationId,
      updatedAt: new Date("2026-08-19T12:00:00.000Z"),
    },
  ],
};

const projector = (): ServingProjector => ({
  applyBalanceTransaction: vi.fn(async () => undefined),
  initializeAccount: vi.fn(async () => undefined),
  projectAccount: vi.fn(async () => undefined),
  projectCredential: vi.fn(async () => undefined),
  projectModel: vi.fn(async () => undefined),
  projectWorkspace: vi.fn(async () => undefined),
});

describe("serving-state reconciliation", () => {
  it("refreshes current projections and pages every eligible balance transaction", async () => {
    const reader: ServingReconciliationReader = {
      getProjectionSnapshot: vi.fn(async () => snapshot),
      getBalanceTransactions: vi
        .fn()
        .mockResolvedValueOnce([firstTransaction, secondTransaction])
        .mockResolvedValueOnce([thirdTransaction]),
    };
    const target = projector();

    await expect(reconcileServingStatePass(reader, target, 2)).resolves.toEqual(
      {
        accounts: 1,
        balanceTransactions: 3,
        credentials: 1,
        models: 1,
        workspaces: 1,
      },
    );

    expect(target.projectAccount).toHaveBeenCalledWith(snapshot.accounts[0]);
    expect(target.initializeAccount).not.toHaveBeenCalled();
    expect(target.projectWorkspace).toHaveBeenCalledWith(
      snapshot.workspaces[0],
    );
    expect(target.projectCredential).toHaveBeenCalledWith(
      snapshot.credentials[0]?.digestHex,
      snapshot.credentials[0]?.credential,
    );
    expect(target.projectModel).toHaveBeenCalledWith(snapshot.models[0]);
    expect(reader.getBalanceTransactions).toHaveBeenNthCalledWith(
      1,
      undefined,
      2,
    );
    expect(reader.getBalanceTransactions).toHaveBeenNthCalledWith(
      2,
      { createdAt: secondTransaction.createdAt, id: secondTransaction.id },
      2,
    );
    expect(target.applyBalanceTransaction).toHaveBeenNthCalledWith(1, {
      amount: firstTransaction.amount,
      organizationId: firstTransaction.organizationId,
      transactionId: firstTransaction.id,
    });
    expect(target.applyBalanceTransaction).toHaveBeenCalledTimes(3);
  });

  it("starts each periodic pass from the first transaction", async () => {
    const abortController = new AbortController();
    const reader: ServingReconciliationReader = {
      getProjectionSnapshot: vi.fn(async () => ({
        accounts: [],
        credentials: [],
        models: [],
        workspaces: [],
      })),
      getBalanceTransactions: vi.fn(async () => []),
    };
    const onReady = vi.fn(async () => {
      if (vi.mocked(reader.getProjectionSnapshot).mock.calls.length === 2) {
        abortController.abort();
      }
    });

    await runServingReconciliationLoop(
      reader,
      projector(),
      {
        balanceTransactionBatchSize: 100,
        onReady,
        pollMilliseconds: 1,
      },
      abortController.signal,
    );

    expect(reader.getBalanceTransactions).toHaveBeenCalledTimes(2);
    expect(reader.getBalanceTransactions).toHaveBeenNthCalledWith(
      1,
      undefined,
      100,
    );
    expect(reader.getBalanceTransactions).toHaveBeenNthCalledWith(
      2,
      undefined,
      100,
    );
    expect(onReady).toHaveBeenCalledTimes(2);
  });
});
