import type {
  ServingProjector,
  ServingReconciliationReader,
} from "@gradiated/control";

export type ServingReconciliationOptions = {
  balanceTransactionBatchSize: number;
  onReady?: (() => Promise<void>) | undefined;
  pollMilliseconds: number;
};

export type ServingReconciliationResult = {
  accounts: number;
  balanceTransactions: number;
  credentials: number;
  models: number;
  workspaces: number;
};

export const reconcileServingStatePass = async (
  reader: ServingReconciliationReader,
  projector: ServingProjector,
  balanceTransactionBatchSize: number,
): Promise<ServingReconciliationResult> => {
  const snapshot = await reader.getProjectionSnapshot();

  for (const account of snapshot.accounts) {
    await projector.projectAccount(account);
  }
  for (const workspace of snapshot.workspaces) {
    await projector.projectWorkspace(workspace);
  }
  for (const { digestHex, credential } of snapshot.credentials) {
    await projector.projectCredential(digestHex, credential);
  }
  for (const model of snapshot.models) {
    await projector.projectModel(model);
  }

  let balanceTransactionCount = 0;
  let cursor: { createdAt: Date; id: string } | undefined;
  while (true) {
    const transactions = await reader.getBalanceTransactions(
      cursor,
      balanceTransactionBatchSize,
    );
    for (const transaction of transactions) {
      await projector.applyBalanceTransaction({
        amount: transaction.amount,
        organizationId: transaction.organizationId,
        transactionId: transaction.id,
      });
    }
    balanceTransactionCount += transactions.length;
    const last = transactions.at(-1);
    if (!last || transactions.length < balanceTransactionBatchSize) break;
    cursor = { createdAt: last.createdAt, id: last.id };
  }

  return {
    accounts: snapshot.accounts.length,
    balanceTransactions: balanceTransactionCount,
    credentials: snapshot.credentials.length,
    models: snapshot.models.length,
    workspaces: snapshot.workspaces.length,
  };
};

const wait = async (
  milliseconds: number,
  signal: AbortSignal,
): Promise<void> => {
  await new Promise<void>((resolve) => {
    const timeout = setTimeout(resolve, milliseconds);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timeout);
        resolve();
      },
      { once: true },
    );
  });
};

export const runServingReconciliationLoop = async (
  reader: ServingReconciliationReader,
  projector: ServingProjector,
  options: ServingReconciliationOptions,
  signal: AbortSignal,
): Promise<void> => {
  while (!signal.aborted) {
    await reconcileServingStatePass(
      reader,
      projector,
      options.balanceTransactionBatchSize,
    );
    await options.onReady?.();
    await wait(options.pollMilliseconds, signal);
  }
};
