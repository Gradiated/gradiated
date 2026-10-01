import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { reconcileTemplates, templateRequests } from "./runpod-templates.mjs";

const config = JSON.parse(
  readFileSync(
    new URL(
      "../../infra/environments/prod/runpod/templates.json",
      import.meta.url,
    ),
    "utf8",
  ),
);
const requests = templateRequests(config, config.image);
const page = (templates, nextCursor = null) => ({
  templates,
  pagination: { hasNextPage: nextCursor !== null, nextCursor },
});

test("rejects digest references and images that differ from enrollment", () => {
  assert.throws(() =>
    templateRequests(
      { ...config, image: "inference@sha256:123" },
      "inference@sha256:123",
    ),
  );
  assert.throws(() => templateRequests(config, "another-image"));
});

test("templates start the host image without shared credentials or model commands", () => {
  for (const request of requests) {
    assert.equal(request.args, "");
    assert.deepEqual(request.env, {});
    assert.equal(request.startSsh, true);
    assert.equal(request.startJupyter, false);
    assert.equal(request.public, false);
    assert.equal(request.registry, null);
    assert.ok(request.ports.includes("22/tcp"));
    assert.ok(request.ports.includes("8888/http"));
  }
});

test("check is read-only and apply only creates missing templates", async () => {
  const calls = [];
  const call = async (method, path, body) => {
    calls.push({ method, path });
    if (method === "GET") return page([]);
    assert.equal(method, "POST");
    assert.equal(path, "/templates");
    return { ...body, id: `template-${calls.length}` };
  };
  const check = await reconcileTemplates(requests, call, false);
  assert.ok(check.every((item) => item.status === "missing"));
  assert.deepEqual(calls, [{ method: "GET", path: "/templates" }]);

  const applied = await reconcileTemplates(requests, call, true);
  assert.ok(applied.every((item) => item.status === "created" && item.id));
  assert.equal(calls.filter((item) => item.method === "POST").length, requests.length);
});

test("finds existing templates across pages without mutating them", async () => {
  const existing = requests.map((request, index) => ({
    ...request,
    id: `template-${index}`,
  }));
  const paths = [];
  const result = await reconcileTemplates(
    requests,
    async (method, path) => {
      assert.equal(method, "GET");
      paths.push(path);
      return path === "/templates"
        ? page(existing.slice(0, 1), "next/page")
        : page(existing.slice(1));
    },
    true,
  );
  assert.deepEqual(paths, ["/templates", "/templates?cursor=next%2Fpage"]);
  assert.ok(result.every((item) => item.status === "unchanged"));
});

test("drift or duplicate names fail before creating any missing template", async () => {
  for (const existing of [
    [{ ...requests[2], disk: 10 }],
    [requests[2], requests[2]],
  ]) {
    await assert.rejects(
      reconcileTemplates(
        requests,
        async (method) => {
          assert.equal(method, "GET");
          return page(existing);
        },
        true,
      ),
    );
  }
});
