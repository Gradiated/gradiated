import type { ModelDeploymentRelease } from "@gradiated/contracts";
import { ControlServiceError } from "../errors.js";
import type { TaskVersionRecord } from "./records.js";

/** A LoRA-enabled serving allocation whose loader can probe an adapter. */
export interface AdapterProbeTarget {
  readonly id: string;
  readonly modelId: string;
  readonly serviceUrl: string;
  readonly release: ModelDeploymentRelease;
}

/**
 * One loader probe: prepare the adapter on the allocation, then run a bounded
 * generation through its engine. `rejected` means the loader or runtime refused
 * the adapter itself; any other failure is about that allocation.
 */
export type AdapterProbeOutcome =
  | { readonly ok: true }
  | { readonly ok: false; readonly rejected: boolean; readonly reason: string };

export type AdapterProbe = (
  target: AdapterProbeTarget,
  adapter: { readonly workspaceId: string; readonly versionId: string },
) => Promise<AdapterProbeOutcome>;

export type AdapterQualificationOutcome =
  "passed" | "rejected" | "failed" | "no_capacity";

export interface AdapterQualificationResult {
  readonly outcome: AdapterQualificationOutcome;
  readonly reason?: string;
  readonly modelId: string;
  readonly workspaceId: string;
  readonly versionId: string;
  /** The allocation that passed, or the last one tried. */
  readonly deploymentId?: string;
  readonly attempts: number;
  readonly durationMs: number;
}

export type AdapterQualifier = (version: TaskVersionRecord) => Promise<void>;

/** The revision the gateway compares with each deployment's LoRA base revision. */
export const adapterBaseRevision = (version: TaskVersionRecord) =>
  version.adapter.validated_base_model_revision ??
  version.adapter.base_model_revision;

/** Mirrors the gateway's rule for which deployments may serve an adapter. */
export const servesAdapter = (
  release: ModelDeploymentRelease,
  revision: string | undefined,
) =>
  release.lora_enabled === true &&
  !!revision &&
  (release.lora_base_model_revision ?? release.model_revision) === revision &&
  release.protocol !== "system_one" &&
  !release.runtime_revision.startsWith("native-");

const shuffled = <T>(items: readonly T[]) => {
  const copy = [...items];
  for (let index = copy.length - 1; index > 0; index--) {
    const other = Math.floor(Math.random() * (index + 1));
    [copy[index], copy[other]] = [copy[other]!, copy[index]!];
  }
  return copy;
};

/**
 * Qualifies an adapter for serving by probing it on one LoRA-enabled allocation
 * of its base model. A failed allocation moves on to the next, up to
 * `maxAttempts`; the first success qualifies the version. Other allocations load
 * the adapter on their first request.
 */
export const createAdapterQualifier = ({
  targets,
  probe,
  report = () => undefined,
  maxAttempts = 3,
  now = Date.now,
  order = shuffled,
}: {
  targets: (modelId: string) => Promise<AdapterProbeTarget[]>;
  probe: AdapterProbe;
  report?: (result: AdapterQualificationResult) => void;
  maxAttempts?: number;
  now?: () => number;
  order?: <T>(items: readonly T[]) => T[];
}): AdapterQualifier => {
  return async (version) => {
    const started = now();
    const revision = adapterBaseRevision(version);
    const identity = {
      modelId: version.baseModelId,
      workspaceId: version.workspaceId,
      versionId: version.id,
    };
    const finish = (
      outcome: AdapterQualificationOutcome,
      attempts: number,
      deploymentId?: string,
      reason?: string,
    ) =>
      report({
        ...identity,
        outcome,
        attempts,
        durationMs: now() - started,
        ...(deploymentId ? { deploymentId } : {}),
        ...(reason ? { reason } : {}),
      });

    const candidates = order(
      (await targets(version.baseModelId)).filter((target) =>
        servesAdapter(target.release, revision),
      ),
    ).slice(0, maxAttempts);
    if (!candidates.length) {
      finish("no_capacity", 0);
      throw new ControlServiceError(
        "unavailable",
        "No serving capacity for this base model can load adapters right now. Try again later.",
      );
    }

    let rejected = false;
    let reason = "probe_failed";
    let attempts = 0;
    for (const target of candidates) {
      attempts += 1;
      const result: AdapterProbeOutcome = await probe(target, {
        workspaceId: version.workspaceId,
        versionId: version.id,
      }).catch(() => ({ ok: false, rejected: false, reason: "probe_error" }));
      if (result.ok) {
        finish("passed", attempts, target.id);
        return;
      }
      rejected ||= result.rejected;
      reason = result.reason;
      if (attempts === candidates.length) {
        finish(rejected ? "rejected" : "failed", attempts, target.id, reason);
      }
    }

    throw rejected
      ? new ControlServiceError(
          "conflict",
          "The serving runtime could not load this adapter. Check that it targets modules this base model supports. The version was not promoted.",
        )
      : new ControlServiceError(
          "unavailable",
          "The adapter could not be tested on serving capacity. Try again shortly. The version was not promoted.",
        );
  };
};
