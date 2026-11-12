import type {
  AdapterProbe,
  AdapterProbeOutcome,
  AdapterQualificationResult,
} from "@gradiated/control";
import { serviceLog } from "../logging.js";
import type { ApiMetrics } from "../metrics.js";

// A cold probe shares the loader's 60-second preparation deadline, then runs a
// bounded generation whose engine call the loader caps at another 60 seconds.
export const ADAPTER_PROBE_TIMEOUT_MS = 150_000;

const LOADER_ERRORS = new Set([
  "capacity_unavailable",
  "adapter_unavailable",
  "preparation_failed",
  "invalid_adapter",
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

/**
 * Calls the allocation loader's `POST /internal/adapters/probe` through the
 * host proxy. The loader prepares the adapter (grant, download, verification),
 * then generates through its engine and checks the returned identity and usage.
 */
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

/** Logs and counts every qualification without adapter or prompt contents. */
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
