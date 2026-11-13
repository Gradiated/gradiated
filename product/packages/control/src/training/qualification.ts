import type { ModelDeploymentRelease } from "@gradiated/contracts";
import { ControlServiceError } from "../errors.js";
import type { TaskVersionRecord } from "./records.js";

export interface AdapterProbeTarget {
  readonly id: string;
  readonly modelId: string;
  readonly serviceUrl: string;
  readonly release: ModelDeploymentRelease;
}

// `rejected`: the loader or runtime refused the adapter, not just this allocation.
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
  readonly deploymentId?: string;
  readonly attempts: number;
  readonly durationMs: number;
}

export type AdapterQualifier = (version: TaskVersionRecord) => Promise<void>;

// Resolves to a release function, or undefined when another request holds the version.
export type QualificationLock = (
  versionId: string,
) => Promise<(() => Promise<void>) | undefined>;

export const adapterBaseRevision = (version: TaskVersionRecord) =>
  version.adapter.validated_base_model_revision ??
  version.adapter.base_model_revision;

// Must match the gateway's rule for deployments that may serve an adapter.
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

export const createAdapterQualifier = ({
  targets,
  probe,
  report = () => undefined,
  maxTargets = 8,
  now = Date.now,
  order = shuffled,
}: {
  targets: (modelId: string) => Promise<AdapterProbeTarget[]>;
  probe: AdapterProbe;
  report?: (result: AdapterQualificationResult) => void;
  maxTargets?: number;
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
    ).slice(0, maxTargets);
    if (!candidates.length) {
      finish("no_capacity", 0);
      throw new ControlServiceError(
        "unavailable",
        "No serving capacity for this base model can load adapters right now. Try again later.",
      );
    }

    // Every allocation is probed so one that refuses the adapter is never skipped.
    const results = await Promise.all(
      candidates.map(async (target) => ({
        target,
        result: await probe(target, {
          workspaceId: version.workspaceId,
          versionId: version.id,
        }).catch((): AdapterProbeOutcome => ({
          ok: false,
          rejected: false,
          reason: "probe_error",
        })),
      })),
    );
    const rejection = results.find(
      ({ result }) => !result.ok && result.rejected,
    );
    if (rejection && !rejection.result.ok) {
      finish(
        "rejected",
        results.length,
        rejection.target.id,
        rejection.result.reason,
      );
      throw new ControlServiceError(
        "conflict",
        "The serving runtime could not load this adapter. Check that it targets modules this base model supports. The version was not promoted.",
      );
    }

    const passed = results.find(({ result }) => result.ok);
    if (passed) {
      finish("passed", results.length, passed.target.id);
      return;
    }

    const last = results.at(-1)!;
    finish(
      "failed",
      results.length,
      last.target.id,
      last.result.ok ? undefined : last.result.reason,
    );

    throw new ControlServiceError(
      "unavailable",
      "The adapter could not be tested on serving capacity. Try again shortly. The version was not promoted.",
    );
  };
};
