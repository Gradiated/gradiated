import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execute = promisify(execFile);

const OWNER_LABEL = "gateway-contract";
const COMMAND_TIMEOUT_MS = 120_000;

/**
 * Pin the daemon to this host's own unix socket. Remote contexts are deliberately
 * refused: these containers must never be created on a shared or remote engine.
 */
const localHost = async (): Promise<string> => {
  const configured =
    process.env.DOCKER_HOST ??
    (await execute("docker", [
      "context",
      "inspect",
      "--format",
      "{{.Endpoints.docker.Host}}",
    ])
      .then(({ stdout }) => stdout.trim())
      .catch(() => "unix:///var/run/docker.sock"));

  if (!configured.startsWith("unix://")) {
    throw new Error(`refusing a non-local Docker endpoint: ${configured}`);
  }

  return configured;
};

export class LocalDocker {
  readonly #host: string;
  readonly #containers: string[] = [];

  private constructor(
    host: string,
    readonly owner: string,
  ) {
    this.#host = host;
  }

  static async connect(owner: string): Promise<LocalDocker> {
    return new LocalDocker(await localHost(), owner);
  }

  async command(...args: string[]): Promise<string> {
    const { stdout } = await execute(
      "docker",
      ["--host", this.#host, ...args],
      {
        timeout: COMMAND_TIMEOUT_MS,
      },
    );

    return stdout.trim();
  }

  /**
   * Both streams, for output a person reads. `docker logs` relays the container's
   * stderr to ours, so a server that failed with a traceback says nothing on stdout.
   */
  async output(...args: string[]): Promise<string> {
    const { stdout, stderr } = await execute(
      "docker",
      ["--host", this.#host, ...args],
      { timeout: COMMAND_TIMEOUT_MS, maxBuffer: 8 * 1024 * 1024 },
    );

    return `${stdout}${stderr}`.trim();
  }

  async run(role: string, args: readonly string[]): Promise<string> {
    const name = `${this.owner}-${role}`;
    // Registered before the container exists, so a failure during startup still
    // leaves teardown able to remove it rather than stranding it running.
    this.#containers.push(name);

    await this.command(
      "run",
      "-d",
      "--name",
      name,
      "--label",
      `${OWNER_LABEL}=${this.owner}`,
      ...args,
    );

    return name;
  }

  async running(name: string): Promise<boolean> {
    return (
      (await this.command(
        "inspect",
        "--format",
        "{{.State.Running}}",
        name,
      )) === "true"
    );
  }

  /** Removes, newest first, only the containers whose label proves this run owns them. */
  async removeOwned(): Promise<void> {
    for (const name of this.#containers.splice(0).reverse()) {
      const owner = await this.command(
        "inspect",
        "--format",
        `{{index .Config.Labels "${OWNER_LABEL}"}}`,
        name,
      ).catch(() => "");

      if (owner === this.owner) {
        await this.command("rm", "-f", "-v", name).catch(() => "");
      }
    }
  }
}
