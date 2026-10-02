import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";

import { chatChunks } from "./chat.js";
import { useCases, type Case } from "./case.js";
import { deferred, eventually } from "./eventually.js";

const { makeCase } = useCases();

const enable = async (
  instance: Case,
  loraBaseRevision?: string,
): Promise<string> => {
  const release = {
    ...instance.release,
    lora_enabled: true,
    ...(loraBaseRevision ? { lora_base_model_revision: loraBaseRevision } : {}),
  };
  for (const deployment of instance.deployments) deployment.release = release;
  await instance.publish();
  const digest = `sha256:${createHash("sha256").update(JSON.stringify(release)).digest("hex")}`;
  await instance.redis.hSet(
    `deployment-status:{${digest}}`,
    Object.fromEntries(
      instance.deployments.map((deployment) => [
        deployment.id,
        JSON.stringify({
          schema_version: 1,
          deployment_id: deployment.id,
          runtime_revision: release.runtime_revision,
          received_at: new Date().toISOString(),
          healthy: true,
          accepting_requests: true,
          reason_code: null,
        }),
      ]),
    ),
  );
  return digest;
};

const version = async (
  instance: Case,
  task = crypto.randomUUID(),
  baseRevision = instance.release.model_revision,
) => {
  const id = crypto.randomUUID();
  const run = crypto.randomUUID();
  const sha256 = "a".repeat(64);
  await instance.database.query(
    "insert into tasks (id, workspace_id, name, base_model_id) values ($1, $2, $3, $4) on conflict (id) do nothing",
    [task, instance.workspace, `task-${task}`, instance.model],
  );
  await instance.database.query(
    "insert into training_runs (id, task_id, trigger, stage, base_model_id, input_cutoff, finished_at) values ($1, $2, 'manual', 'succeeded', $3, now(), now())",
    [run, task, instance.model],
  );
  await instance.database.query(
    "insert into task_versions (id, workspace_id, task_id, training_run_id, name, base_model_id, adapter, status) values ($1, $2, $3, $4, $5, $6, $7, 'available')",
    [
      id,
      instance.workspace,
      task,
      run,
      `version-${id}`,
      instance.model,
      JSON.stringify({
        format: "peft_lora",
        artifact_uri: `s3://synthetic/runs/${run}/adapter.tar.gz`,
        sha256,
        size_bytes: 10,
        rank: 2,
        base_model_revision: baseRevision,
      }),
    ],
  );
  return {
    id,
    task,
    sha256,
    selector: `version-${id}`,
    runtimeName: `${instance.workspace}/version-${id}`,
  };
};

const production = (
  instance: Case,
  selected: Awaited<ReturnType<typeof version>>,
) =>
  instance.database.query(
    "update tasks set production_version_id = $2 where id = $1",
    [selected.task, selected.id],
  );

const settlement = (instance: Case, generation: string | undefined) =>
  eventually(
    async () =>
      (await instance.settlements()).find(
        (row) => row.generation === generation,
      )?.properties,
    5000,
    "adapter settlement missing",
  );

describe("workspace-private adapters", () => {
  it("serves a separately qualified training revision and rejects it without qualification", async () => {
    const qualified = await makeCase("vllm");
    await enable(qualified, "training-bf16-revision");
    const selected = await version(
      qualified,
      crypto.randomUUID(),
      "training-bf16-revision",
    );
    const response = await qualified.post({ model: selected.selector });
    expect(response.status).toBe(200);
    expect(qualified.runtimes[0]!.calls[0]!.model).toBe(selected.runtimeName);

    const unqualified = await makeCase("vllm");
    await enable(unqualified);
    const rejected = await version(
      unqualified,
      crypto.randomUUID(),
      "training-bf16-revision",
    );
    expect((await unqualified.post({ model: rejected.selector })).status).toBe(
      404,
    );
    expect(unqualified.totalCalls()).toBe(0);
  });

  it("sends normal inference for a private version and records exact identity with base pricing", async () => {
    const instance = await makeCase("vllm");
    const digest = await enable(instance);
    const selected = await version(instance);
    const response = await instance.post({ model: selected.selector });
    expect(response.status).toBe(200);
    expect(response.json().model).toBe(selected.selector);
    expect(instance.totalCalls()).toBe(1);
    expect(instance.runtimes[0]!.calls[0]!.model).toBe(selected.runtimeName);
    const stored = await settlement(
      instance,
      response.headers["x-gradiated-generation-id"],
    );
    expect(stored.model_id).toBe(selected.selector);
    expect(stored.served_release_digest).not.toBe(digest);
    expect(stored.workspace_id).toBe(instance.workspace);
    expect(await instance.charged()).toBeGreaterThan(0);
  });

  it("reads promotion once and keeps the pinned adapter across replica retries", async () => {
    const instance = await makeCase("vllm", { replicas: 2 });
    await enable(instance);
    const first = await version(instance);
    const next = await version(instance, first.task);
    await production(instance, first);
    const warm = await instance.post({
      model: `task-${first.task}`,
      session_id: "same",
    });
    expect(warm.json().model).toBe(first.selector);
    const selected = instance.runtimes.find(
      (runtime) => runtime.calls.length === 1,
    )!;
    const gate = deferred();
    const attempt = selected.enqueue({ status: 503, gate });
    const retrying = instance.post({
      model: `task-${first.task}`,
      session_id: "same",
    });
    await attempt.entered.promise;
    await production(instance, next);
    gate.resolve();
    const retried = await retrying;
    expect(retried.status).toBe(200);
    expect(retried.json().model).toBe(first.selector);
    for (const runtime of instance.runtimes) {
      expect(
        runtime.calls.every((body) => body.model === first.runtimeName),
      ).toBe(true);
    }
    const promoted = await instance.post({
      model: `task-${first.task}`,
    });
    expect(promoted.json().model).toBe(next.selector);
    await settlement(instance, promoted.headers["x-gradiated-generation-id"]);
  });

  it("keeps a streaming request on its exact version after promotion", async () => {
    const instance = await makeCase("vllm");
    await enable(instance);
    const first = await version(instance);
    const next = await version(instance, first.task);
    await production(instance, first);
    const response = await instance.http.stream(instance.path, {
      headers: instance.headers,
      json: instance.body({
        model: `task-${first.task}`,
        stream: true,
      }),
    });
    expect(response.status).toBe(200);
    await production(instance, next);
    const frames = await response.dataFrames();
    expect(frames.at(-1)).toBe("[DONE]");
    expect(
      chatChunks(frames).every((chunk) => chunk.model === first.selector),
    ).toBe(true);
    expect(instance.runtimes[0]!.calls[0]!.model).toBe(first.runtimeName);
    expect(
      (
        await settlement(
          instance,
          response.headers["x-gradiated-generation-id"],
        )
      ).model_id,
    ).toBe(first.selector);
  });

  it("does not reveal private versions to other workspaces or the model catalog", async () => {
    const owner = await makeCase("vllm");
    const other = await makeCase("vllm");
    await enable(owner);
    const selected = await version(owner);
    await production(owner, selected);
    for (const model of [selected.selector, `task-${selected.task}`]) {
      expect((await other.post({ model })).status).toBe(404);
    }
    await other.expectNotDispatched();
    const catalog = await owner.http.get("/v1/models", {
      headers: owner.headers,
    });
    expect(catalog.text).not.toContain(selected.id);
  });

  it("rejects unavailable or legacy versions and unqualified base deployments", async () => {
    const instance = await makeCase("vllm");
    const selected = await version(instance);
    expect((await instance.post({ model: selected.selector })).status).toBe(
      404,
    );
    await enable(instance);
    await instance.database.query(
      "update task_versions set status = 'unavailable' where id = $1",
      [selected.id],
    );
    expect((await instance.post({ model: selected.selector })).status).toBe(
      404,
    );
    await instance.database.query(
      "update task_versions set status = 'available', adapter = adapter - 'base_model_revision' where id = $1",
      [selected.id],
    );
    expect((await instance.post({ model: selected.selector })).status).toBe(
      404,
    );
    await instance.expectNotDispatched();
  });

  it("rejects ambiguous task and version slugs instead of choosing an adapter", async () => {
    const instance = await makeCase("vllm");
    await enable(instance);
    const exact = await version(instance);
    const other = await version(instance);
    await instance.database.query(
      "update tasks set name = $2, production_version_id = $3 where id = $1",
      [other.task, exact.selector, other.id],
    );
    expect((await instance.post({ model: exact.selector })).status).toBe(503);
    await instance.database.query(
      "update tasks set production_version_id = null where id = $1",
      [other.task],
    );
    expect((await instance.post({ model: exact.selector })).status).toBe(503);
    await instance.expectNotDispatched();
  });

  it("serves long task/version slugs and retains them in settlement", async () => {
    const instance = await makeCase("vllm");
    await enable(instance);
    const selected = await version(instance);
    const task = "a".repeat(256);
    const name = `${task}-20261002-2`;
    await instance.database.query(
      "update tasks set name = $2, production_version_id = $3 where id = $1",
      [selected.task, task, selected.id],
    );
    await instance.database.query(
      "update task_versions set name = $2 where id = $1",
      [selected.id, name],
    );
    for (const model of [task, name]) {
      const response = await instance.post({ model });
      expect(response.status).toBe(200);
      expect(response.json().model).toBe(name);
      expect(instance.runtimes[0]!.calls.at(-1)!.model).toBe(
        `${instance.workspace}/${name}`,
      );
      expect(
        (
          await settlement(
            instance,
            response.headers["x-gradiated-generation-id"],
          )
        ).model_id,
      ).toBe(name);
    }
  });

  it("rejects public catalog name collisions even without a production pointer", async () => {
    const instance = await makeCase("vllm");
    await enable(instance);
    const selected = await version(instance);
    await instance.database.query(
      "update tasks set name = $2, production_version_id = $3 where id = $1",
      [selected.task, instance.model, selected.id],
    );
    expect((await instance.post({ model: instance.model })).status).toBe(503);
    await instance.database.query(
      "update tasks set production_version_id = null where id = $1",
      [selected.task],
    );
    expect((await instance.post({ model: instance.model })).status).toBe(503);
    await instance.expectNotDispatched();
  });

  it("does not charge when host-side resolution fails", async () => {
    const instance = await makeCase("vllm");
    await enable(instance);
    const selected = await version(instance);
    instance.runtimes[0]!.resolutionStatus = 500;
    const response = await instance.post({ model: selected.selector });
    expect(response.status).toBe(503);
    expect(instance.totalCalls()).toBe(1);
    const stored = await settlement(
      instance,
      response.headers["x-gradiated-generation-id"],
    );
    expect(stored.status).toBe("failed");
    expect(await instance.charged()).toBe(0);
  });
});
