import type { Condition, GpuHost, HostStatus } from "./hosts.js";
import type { Observation } from "./observe.js";

// A host may miss pings this long before it is reported Degraded, so a brief
// network blip or agent restart does not page anyone.
export const UNREACHABLE_AFTER_MS = 2 * 60_000;

export type Problem = { reason: string; message: string };

export type HostFindings = {
  observation: Observation;
  serviceError?: string;
  conflict?: string;
  // Pods still running on a deleted host.
  draining?: number;
  // The latest successful ping this replica saw, newer than the persisted one.
  lastAnswered?: string;
  // When this replica took the lease. A new leader has seen no pings yet, so it
  // waits out its own grace period before reporting a host Unreachable.
  leadingSince?: string;
};

const problem = (
  host: GpuHost,
  findings: HostFindings,
  lastSeen: string | undefined,
  now: Date,
): Problem | undefined => {
  if (findings.conflict)
    return { reason: "PostgresConflict", message: findings.conflict };
  const rollout = host.status?.rollout;
  // A failed lease is the holder's outcome; the host never left the pool.
  if (rollout?.result === "Failed" && rollout.kind !== "lease")
    return {
      reason: "RolloutFailed",
      message: `The ${rollout.kind} rollout failed at ${rollout.step}: ${rollout.lastError ?? "no reason recorded"}`,
    };
  if (findings.serviceError)
    return { reason: "ServiceFailed", message: findings.serviceError };
  const { observation } = findings;
  if (observation.reachable && observation.instanceId !== host.spec.instanceId)
    return {
      reason: "IdentityMismatch",
      message: `The host agent reports instance ${observation.instanceId}`,
    };
  if (observation.reachable) return;
  const since = Math.max(
    ...[lastSeen ?? host.metadata.creationTimestamp, findings.leadingSince]
      .map((time) => Date.parse(time ?? ""))
      .filter(Number.isFinite),
  );
  if (!(now.getTime() - since < UNREACHABLE_AFTER_MS))
    return { reason: "Unreachable", message: observation.error };
};

const condition = (
  previous: Condition[] | undefined,
  type: Condition["type"],
  status: Condition["status"],
  reason: string,
  message: string,
  now: Date,
): Condition => {
  const before = previous?.find((item) => item.type === type);
  return {
    type,
    status,
    reason,
    message,
    lastTransitionTime:
      before?.status === status ? before.lastTransitionTime : now.toISOString(),
  };
};

export const hostStatus = (
  host: GpuHost,
  findings: HostFindings,
  now: Date,
): HostStatus => {
  const previous = host.status;
  const { observation } = findings;
  const lastSeen = observation.reachable
    ? now.toISOString()
    : (findings.lastAnswered ?? previous?.observed?.lastSeen);
  const hostBundleSha256 = observation.reachable
    ? observation.hostBundleSha256
    : previous?.observed?.hostBundleSha256;
  const found = problem(host, findings, lastSeen, now);
  const draining = findings.draining;
  // Within the grace period an unanswered ping keeps the previous phase.
  const phase =
    draining !== undefined
      ? "Draining"
      : found
        ? "Degraded"
        : observation.reachable
          ? "Ready"
          : (previous?.phase ?? "Pending");
  const readyReason =
    draining !== undefined
      ? {
          reason: "Draining",
          message: `Deleted; held until no pods run on it (${draining} remaining)`,
        }
      : found
        ? found
        : phase === "Ready"
          ? {
              reason: "HostAnswering",
              message: "The host agent answers and its Service is in place",
            }
          : {
              reason: "WaitingForHost",
              message: "The host agent has not answered yet",
            };

  return {
    observedGeneration: host.metadata.generation,
    phase,
    observed: {
      reachable: observation.reachable,
      ...(lastSeen && { lastSeen }),
      ...(hostBundleSha256 !== undefined && { hostBundleSha256 }),
    },
    conditions: [
      condition(
        previous?.conditions,
        "Ready",
        phase === "Ready" ? "True" : phase === "Pending" ? "Unknown" : "False",
        readyReason.reason,
        readyReason.message,
        now,
      ),
      condition(
        previous?.conditions,
        "Degraded",
        found ? "True" : "False",
        found?.reason ?? "AsExpected",
        found?.message ?? "No problems found",
        now,
      ),
    ],
  };
};
