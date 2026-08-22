import type {
  ServingProjector,
  ServingProjectionReader,
} from "@gradiated/control";

export type ServingProjectorOptions = {
  balanceTransactionBatchSize: number;
  onReady?: (() => Promise<void>) | undefined;
  onPass?:
    | ((result: ServingProjectionResult, durationSeconds: number) => void)
    | undefined;
  pollMilliseconds: number;
};

export type ServingProjectionResult = {
  accounts: number;
  balanceTransactions: number;
  credentials: number;
  models: number;
  workspaces: number;
};

export const projectServingStatePass = async (
  reader: ServingProjectionReader,
  projector: ServingProjector,
  balanceTransactionBatchSize: number,
): Promise<ServingProjectionResult> => {
  const snapshot = await reader.getProjectionSnapshot();
  const restoredAccountCutoffs = new Map<string, Date>();

  for (const account of snapshot.accounts) {
    if (await projector.projectAccount(account)) {
      restoredAccountCutoffs.set(account.organizationId, account.updatedAt);
    }
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
      const restoredCutoff = restoredAccountCutoffs.get(
        transaction.organizationId,
      );
      if (restoredCutoff && transaction.createdAt <= restoredCutoff) {
        await projector.markBalanceTransactionApplied({
          organizationId: transaction.organizationId,
          transactionId: transaction.id,
        });
      } else {
        await projector.applyBalanceTransaction({
          amount: transaction.amount,
          organizationId: transaction.organizationId,
          transactionId: transaction.id,
        });
      }
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

export const runServingProjectorLoop = async (
  reader: ServingProjectionReader,
  projector: ServingProjector,
  options: ServingProjectorOptions,
  signal: AbortSignal,
): Promise<void> => {
  while (!signal.aborted) {
    const started = process.hrtime.bigint();
    const result = await projectServingStatePass(
      reader,
      projector,
      options.balanceTransactionBatchSize,
    );
    options.onPass?.(result, Number(process.hrtime.bigint() - started) / 1e9);
    await options.onReady?.();
    await wait(options.pollMilliseconds, signal);
  }
};
