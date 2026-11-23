import { randomUUID } from "node:crypto";
import {
  ControlServiceError,
  type AdapterProbe,
  type AdapterProbeOutcome,
  type AdapterQualificationResult,
  type QualificationLock,
} from "@gradiated/control";
import { serviceLog } from "../logging.js";
import type { ApiMetrics } from "../metrics.js";

// Loader worst case: 60 s preparation, a 60 s generation and, for a cartridge, two
// 30 s canary generations (CANARY_TIMEOUT_SECONDS), plus 30 s of slack.
export const ADAPTER_PROBE_TIMEOUT_MS = 210_000;

const LOADER_ERRORS = new Set([
  "capacity_unavailable",
  "adapter_unavailable",
  "preparation_failed",
  "invalid_adapter",
  "cartridge_not_applied",
]);

const probeUrl = (serviceUrl: string) => {
  const url = new URL(
    `${serviceUrl.replace(/\/+$/, "")}/internal/adapters/probe`,
  );
  if (
    (url.protocol !== "http:" && url.protocol !== "https:") ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw new Error("Invalid adapter probe target.");

  return url;
};

export const createAdapterProbe = ({
  fetch = globalThis.fetch,
  timeoutMs = ADAPTER_PROBE_TIMEOUT_MS,
}: {
  fetch?: typeof globalThis.fetch;
  timeoutMs?: number;
} = {}): AdapterProbe => {
  return async (target, adapter): Promise<AdapterProbeOutcome> => {
    let response: Response;
    try {
      response = await fetch(probeUrl(target.serviceUrl), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          // The loader names an adapter by its version ID.
          name: adapter.versionId,
          workspace_id: adapter.workspaceId,
        }),
        redirect: "error",
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (error) {
      return {
        ok: false,
        rejected: false,
        reason:
          error instanceof Error && error.name === "TimeoutError"
            ? "probe_timeout"
            : "probe_unreachable",
      };
    }

    const body: unknown = await response
      .text()
      .then((text) => (text.length <= 65_536 ? JSON.parse(text) : null))
      .catch(() => null);
    const error =
      body && typeof body === "object" && "error" in body
        ? String(body.error)
        : undefined;

    if (
      response.status === 200 &&
      body &&
      typeof body === "object" &&
      "ready" in body &&
      body.ready === true
    )
      return { ok: true };

    return {
      ok: false,
      // The loader answers 422 when it or the runtime rejects the adapter.
      rejected: response.status === 422,
      reason:
        error && LOADER_ERRORS.has(error)
          ? error
          : response.status === 200
            ? "probe_invalid_response"
            : `probe_http_${response.status}`,
    };
  };
};

export const reportAdapterQualification =
  (metrics: Pick<ApiMetrics, "recordAdapterQualification">) =>
  (result: AdapterQualificationResult) => {
    metrics.recordAdapterQualification(
      result.modelId,
      result.outcome,
      result.durationMs / 1_000,
    );
    serviceLog(
      result.outcome === "passed" ? "info" : "warn",
      "adapter_qualification",
      {
        workspace_id: result.workspaceId,
        version_id: result.versionId,
        ...(result.deploymentId ? { deployment_id: result.deploymentId } : {}),
        model_id: result.modelId,
        reason: result.reason
          ? `${result.outcome}/${result.reason}`
          : result.outcome,
        attempt: result.attempts,
        duration_ms: result.durationMs,
      },
    );
  };

// Allocations are probed in parallel, so this outlasts one probe; a holder that
// dies mid-probe blocks retries only briefly.
const QUALIFICATION_LOCK_MS = ADAPTER_PROBE_TIMEOUT_MS + 50_000;
const RELEASE_LOCK = `if redis.call("get", KEYS[1]) == ARGV[1] then return redis.call("del", KEYS[1]) end return 0`;

export const createQualificationLock =
  (valkey: {
    set(
      key: string,
      value: string,
      options: { NX: true; PX: number },
    ): Promise<string | null>;
    eval(
      script: string,
      options: { keys: string[]; arguments: string[] },
    ): Promise<unknown>;
  }): QualificationLock =>
  async (versionId) => {
    const key = `adapter-qualification:{${versionId}}`;
    const token = randomUUID();
    const acquired = await valkey
      .set(key, token, { NX: true, PX: QUALIFICATION_LOCK_MS })
      .catch((error: unknown) => {
        throw new ControlServiceError(
          "unavailable",
          "Serving qualification is temporarily unavailable. The version was not promoted.",
          error,
        );
      });
    if (acquired !== "OK") return undefined;

    return async () => {
      await valkey.eval(RELEASE_LOCK, { keys: [key], arguments: [token] });
    };
  };
