import type { OperationalBalanceReader } from "@gradiated/control";
import type { RedisClientType } from "@gradiated/valkey";

// Matches the gateway's LEDGER_REPLAY_WINDOW: a seed adds every credit this far
// behind its watermark to the applied set.
const ledgerReplayWindowMilliseconds = 30_000;

const settlementHashTag = "settlement-0";

const integer = (value: unknown): bigint | null =>
  typeof value === "string" && /^-?\d+$/.test(value) ? BigInt(value) : null;

export const createOperationalBalanceReader =
  (
    client: Pick<RedisClientType, "hmGet" | "multi">,
  ): OperationalBalanceReader =>
  async (organizationId, creditsSince) => {
    const account = `account:{${settlementHashTag}}:${organizationId}`;
    const applied = `applied-balance-transactions:{${settlementHashTag}}:${organizationId}`;

    const [seededAt] = await client.hmGet(account, ["balance_seeded_at"]);
    const seededAtMilliseconds = integer(seededAt);
    if (seededAtMilliseconds === null) return null;

    const credits = await creditsSince(
      new Date(Number(seededAtMilliseconds) - ledgerReplayWindowMilliseconds),
    );

    // One MULTI reads the balance and the applied set together, so a credit the
    // gateway applies in between is counted exactly once.
    const ids = credits.map((credit) => credit.id);
    const [fields, appliedFlags] =
      ids.length > 0
        ? await client
            .multi()
            .hmGet(account, ["balance", "balance_replay_floor_at"])
            .smIsMember(applied, ids)
            .execTyped()
        : [await client.hmGet(account, ["balance", "balance_replay_floor_at"])];

    const balance = integer(fields[0]);
    if (balance === null) return null;

    const replayFloor = integer(fields[1]);

    return credits.reduce(
      (total, credit, index) =>
        Number(appliedFlags?.[index]) === 1 ||
        (replayFloor !== null &&
          BigInt(credit.createdAt.getTime()) <= replayFloor)
          ? total
          : total + credit.amount,
      balance,
    );
  };
