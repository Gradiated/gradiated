import { eventually, Fatal } from "../eventually.js";
import { freePort } from "../ports.js";
import type { RuntimeKind } from "../mock-runtimes/server.js";
import type { LocalDocker } from "./docker.js";

export interface RealRuntime {
  readonly baseUrl: string;
  readonly model: string;
}

export type RealRuntimes = Partial<Record<RuntimeKind, RealRuntime>>;

interface RuntimeImage {
  readonly image: string;
  /**
   * The id the gateway addresses and that the runtime returns. vLLM answers with
   * its `--served-model-name` rather than echoing, so the two must match.
   */
  readonly model: string;
  readonly ready: string;
  /**
   * One throwaway inference after readiness. A runtime answers its catalog or
   * health route long before it can serve, because the first real request pays
   * model and kernel warmup; without this the first test pays it instead.
   */
  readonly warm: (baseUrl: string, model: string) => Promise<void>;
  readonly dockerArgs: (port: number) => string[];
  readonly args: readonly string[];
}

/**
 * A runtime that refuses a trivial request is broken, and saying so here is far
 * clearer than the test failure it would otherwise cause. The body is read so the
 * connection can be reused rather than left dangling.
 */
const warmRequest = async (url: string, init: RequestInit): Promise<void> => {
  const response = await fetch(url, init);
  const body = await response.text();

  if (!response.ok) {
    throw new Error(
      `warmup rejected with ${response.status}: ${body.slice(0, 300)}`,
    );
  }
};

const CPU_MODEL =
  process.env.GATEWAY_REAL_RUNTIME_MODEL ?? "gradiated/cpu-test-model";
const CPU_WEIGHTS = "Qwen/Qwen2.5-0.5B-Instruct";

// Both images are built from product/inference/runtimes/{vllm,kev}/Dockerfile.cpu
// with their weights baked in, so a run never reaches Hugging Face.
const REAL_RUNTIMES: Record<RuntimeKind, RuntimeImage> = {
  vllm: {
    image: process.env.GATEWAY_REAL_RUNTIME_IMAGE ?? "gradiated/vllm-cpu:ci",
    model: CPU_MODEL,
    ready: "/v1/models",
    warm: async (baseUrl, model) => {
      await warmRequest(`${baseUrl}/v1/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          messages: [{ role: "user", content: "warm" }],
          max_tokens: 1,
        }),
        signal: AbortSignal.timeout(300_000),
      });
    },
    dockerArgs: (port) => [
      "-p",
      `127.0.0.1:${port}:8080`,
      // vLLM's multiprocess executor puts its ring buffer in shared memory and
      // needs 160 MiB of it; Docker's default /dev/shm is 64 MiB.
      "--shm-size=1g",
      "-e",
      // A CI runner has to hold this alongside the gateway, Valkey and the
      // decision runtime.
      "VLLM_CPU_KVCACHE_SPACE=1",
      "-e",
      // Generation is memory-bandwidth bound on a CPU, so starving it of threads
      // is what makes these tests slow.
      "OMP_NUM_THREADS=4",
      "-e",
      // Otherwise a hard kill loses everything the server had not flushed.
      "PYTHONUNBUFFERED=1",
    ],
    args: [
      CPU_WEIGHTS,
      "--served-model-name",
      CPU_MODEL,
      "--host",
      "0.0.0.0",
      "--port",
      "8080",
      "--dtype",
      "float32",
      "--max-model-len",
      "2048",
      "--max-num-seqs",
      "4",
      "--enforce-eager",
      "--scheduling-policy",
      "priority",
      "--enable-prompt-tokens-details",
      "--disable-uvicorn-access-log",
    ],
  },
  // The image runs the adapter we deploy. Upstream's own server reports serialized
  // answer tokens as output and omits cached input, both of which the gateway
  // rejects by design.
  kev: {
    image: process.env.GATEWAY_REAL_KEV_IMAGE ?? "gradiated/kev-cpu:ci",
    model: process.env.GATEWAY_REAL_KEV_MODEL ?? "jaredpalmer/kev-0.5b",
    ready: "/health",
    warm: async (baseUrl, model) => {
      await warmRequest(`${baseUrl}/v1/systemone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          state: "warm",
          questions: { q: { type: "noul", instructions: "warm?" } },
          priority: 0,
        }),
        signal: AbortSignal.timeout(300_000),
      });
    },
    dockerArgs: (port) => ["-p", `127.0.0.1:${port}:8000`],
    args: [],
  },
};

const RUNTIME_READY_TIMEOUT_MS = 240_000;

const awaitReady = async (
  docker: LocalDocker,
  kind: RuntimeKind,
  container: string,
  baseUrl: string,
): Promise<void> => {
  try {
    await eventually(
      async () => {
        if (!(await docker.running(container))) {
          throw new Fatal("the runtime container exited");
        }

        const response = await fetch(`${baseUrl}${REAL_RUNTIMES[kind].ready}`, {
          signal: AbortSignal.timeout(2000),
        });
        return response.ok;
      },
      RUNTIME_READY_TIMEOUT_MS,
      `${kind} real runtime readiness`,
    );
  } catch (error) {
    // An out-of-memory kill leaves no output at all, because Python block-buffers
    // when its stdout is not a terminal. The exit state is what names that case.
    const state = await docker
      .command(
        "inspect",
        "--format",
        "exit={{.State.ExitCode}} oomKilled={{.State.OOMKilled}} error={{.State.Error}}",
        container,
      )
      .catch(() => "(container state unavailable)");
    const logs = await docker
      .output("logs", "--tail", "120", container)
      .catch(() => "(container logs unavailable)");

    throw new Error(
      `${String(error)}\n--- ${kind} container ${state} ---\n${logs || "(no output)"}`,
    );
  }
};

/** GATEWAY_REAL_RUNTIME_URL_VLLM or _KEV points at a server that is already running. */
export const startRealRuntime = async (
  docker: LocalDocker,
  kind: RuntimeKind,
): Promise<RealRuntime> => {
  const spec = REAL_RUNTIMES[kind];
  const existing =
    process.env[`GATEWAY_REAL_RUNTIME_URL_${kind.toUpperCase()}`];

  if (existing) {
    const baseUrl = existing.replace(/\/$/, "");
    await spec.warm(baseUrl, spec.model);
    return { baseUrl, model: spec.model };
  }

  const port = await freePort();
  const container = await docker.run(`runtime-${kind}`, [
    ...spec.dockerArgs(port),
    spec.image,
    ...spec.args,
  ]);
  const baseUrl = `http://127.0.0.1:${port}`;

  await awaitReady(docker, kind, container, baseUrl);
  await spec.warm(baseUrl, spec.model);

  return { baseUrl, model: spec.model };
};
