import { describe, expect, it } from "vitest";

import { enable, production, version } from "./adapter-versions.js";
import { chatChunks } from "./chat.js";
import { useCases, type Case } from "./case.js";
import { deferred, eventually } from "./eventually.js";

const { makeCase } = useCases();

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
  it("serves a separately qualified training revision and serves the base model without one", async () => {
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
    const baseDigest = await enable(unqualified);
    const unservable = await version(
      unqualified,
      crypto.randomUUID(),
      "training-bf16-revision",
    );
    const degraded = await unqualified.post({ model: unservable.selector });
    expect(degraded.status).toBe(200);
    expect(degraded.json().model).toBe(unservable.selector);
    expect(unqualified.runtimes[0]!.calls[0]!.model).toBe(
      unqualified.runtimeModel,
    );
    const stored = await settlement(
      unqualified,
      degraded.headers["x-gradiated-generation-id"],
    );
    expect(stored.model_id).toBe(unservable.selector);
    expect(stored.served_release_digest).toBe(baseDigest);
    expect(stored.usage).toMatchObject({ charge: 1060 });
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
      model: `${instance.organizationSlug}/task-${first.task}`,
      session_id: "same",
    });
    expect(warm.json().model).toBe(first.selector);
    const selected = instance.runtimes.find(
      (runtime) => runtime.calls.length === 1,
    )!;
    const gate = deferred();
    const attempt = selected.enqueue({ status: 503, gate });
    const retrying = instance.post({
      model: `${instance.organizationSlug}/task-${first.task}`,
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
      model: `${instance.organizationSlug}/task-${first.task}`,
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
        model: `${instance.organizationSlug}/task-${first.task}`,
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
    for (const model of [
      selected.selector,
      `${other.organizationSlug}/task-${selected.task}`,
      `task-${selected.task}`,
      selected.name,
    ]) {
      expect((await other.post({ model })).status).toBe(404);
    }
    await other.expectNotDispatched();
    const catalog = await owner.http.get("/v1/models", {
      headers: owner.headers,
    });
    expect(catalog.text).not.toContain(selected.id);
  });

  it("serves the base model without the adapter when no deployment can load it", async () => {
    const instance = await makeCase("vllm");
    const selected = await version(instance);

    const response = await instance.post({ model: selected.selector });

    expect(response.status).toBe(200);
    expect(response.json().model).toBe(selected.selector);
    expect(instance.runtimes[0]!.calls[0]!.model).toBe(instance.runtimeModel);
    const stored = await settlement(
      instance,
      response.headers["x-gradiated-generation-id"],
    );
    expect(stored.model_id).toBe(selected.selector);
    expect(stored.served_release_digest).toBe(instance.digest);
    expect(stored.usage).toMatchObject({ charge: 1060 });
  });

  it("rejects unavailable or legacy versions", async () => {
    const instance = await makeCase("vllm");
    const selected = await version(instance);
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

  it("resolves a model only under its organization's current slug", async () => {
    const instance = await makeCase("vllm");
    await enable(instance);
    const selected = await version(instance);
    await production(instance, selected);
    const moved = `moved-${instance.organization.replaceAll("-", "")}`;
    await instance.database.query(
      "update organizations set slug = $2 where id = $1",
      [instance.organization, moved],
    );

    const response = await instance.post({
      model: `${moved}/task-${selected.task}`,
    });
    expect(response.status).toBe(200);
    expect(response.json().model).toBe(
      `${moved}/task-${selected.task}/${selected.name}`,
    );
    expect(
      (
        await instance.post({
          model: `${instance.organizationSlug}/task-${selected.task}`,
        })
      ).status,
    ).toBe(404);
  });

  it("serves long task/version slugs and retains them in settlement", async () => {
    const instance = await makeCase("vllm");
    await enable(instance);
    const selected = await version(instance);
    const task = "a".repeat(128);
    const name = "2026-10-02-2";
    const model = `${instance.organizationSlug}/${task}/${name}`;
    await instance.database.query(
      "update tasks set name = $2, production_version_id = $3 where id = $1",
      [selected.task, task, selected.id],
    );
    await instance.database.query(
      "update task_versions set name = $2 where id = $1",
      [selected.id, name],
    );
    for (const selector of [`${instance.organizationSlug}/${task}`, model]) {
      const response = await instance.post({ model: selector });
      expect(response.status).toBe(200);
      expect(response.json().model).toBe(model);
      expect(instance.runtimes[0]!.calls.at(-1)!.model).toBe(
        `${instance.workspace}/${task}/${name}`,
      );
      expect(
        (
          await settlement(
            instance,
            response.headers["x-gradiated-generation-id"],
          )
        ).model_id,
      ).toBe(model);
    }
  });

  it("rejects public catalog name collisions even without a production pointer", async () => {
    const instance = await makeCase("vllm");
    await enable(instance);
    const selected = await version(instance);
    const [author, name] = instance.model.split("/");
    await instance.database.query(
      "update organizations set slug = $2 where id = $1",
      [instance.organization, author],
    );
    await instance.database.query(
      "update tasks set name = $2, production_version_id = $3 where id = $1",
      [selected.task, name, selected.id],
    );
    expect((await instance.post({ model: instance.model })).status).toBe(503);
    await instance.database.query(
      "update tasks set production_version_id = null where id = $1",
      [selected.task],
    );
    expect((await instance.post({ model: instance.model })).status).toBe(503);
    await instance.expectNotDispatched();
  });

  it("serves the base model, charged once, when host-side resolution fails", async () => {
    const instance = await makeCase("vllm");
    const baseDigest = await enable(instance);
    const selected = await version(instance);
    instance.runtimes[0]!.resolutionStatus = 500;

    const response = await instance.post({ model: selected.selector });

    expect(response.status).toBe(200);
    expect(response.json().model).toBe(selected.selector);
    expect(instance.runtimes[0]!.calls.map((body) => body.model)).toEqual([
      selected.runtimeName,
      instance.runtimeModel,
    ]);
    const stored = await settlement(
      instance,
      response.headers["x-gradiated-generation-id"],
    );
    expect(stored.status).toBe("succeeded");
    expect(stored.served_release_digest).toBe(baseDigest);
    expect(await instance.charged()).toBe(1060);
  });
});
