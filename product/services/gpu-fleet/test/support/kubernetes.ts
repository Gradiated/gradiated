import { randomUUID } from "node:crypto";

import { KubernetesError, type Kubernetes } from "../../src/kubernetes.js";

type Item = { metadata: Record<string, unknown>; [key: string]: unknown };

const clone = <T>(value: T): T => structuredClone(value);

// RFC 7386 JSON merge patch: objects merge, null removes, anything else replaces.
const merge = (target: unknown, patch: unknown): unknown => {
  if (patch === null || typeof patch !== "object" || Array.isArray(patch))
    return clone(patch);
  const result: Record<string, unknown> =
    target && typeof target === "object" && !Array.isArray(target)
      ? { ...(target as Record<string, unknown>) }
      : {};
  for (const [key, value] of Object.entries(patch)) {
    if (value === null) delete result[key];
    else result[key] = merge(result[key], value);
  }
  return result;
};

/**
 * An in-memory API server with the behavior the operator depends on: objects
 * carry resourceVersions, an update with a stale resourceVersion or a create
 * of an existing name fails with 409, merge patches follow RFC 7386, and the
 * status subresource is written only through `<object>/status`. A spec change
 * bumps metadata.generation.
 */
export const fakeKubernetes = () => {
  const objects = new Map<string, Item>();
  let version = 1;
  const calls: { method: string; path: string }[] = [];

  const store = (path: string, item: Item) => {
    // An object being deleted goes once its last finalizer is removed.
    const finalizers = item.metadata.finalizers as string[] | undefined;
    if (item.metadata.deletionTimestamp && !finalizers?.length) {
      objects.delete(path);
      return clone(item);
    }
    item.metadata.resourceVersion = String(++version);
    objects.set(path, item);
    return clone(item);
  };
  const missing = (path: string) =>
    new KubernetesError(404, `Kubernetes ${path} returned 404`);

  const api: Kubernetes = {
    async get(path) {
      calls.push({ method: "GET", path });
      const item = objects.get(path.replace(/\/status$/, ""));
      return item && clone(item);
    },
    async list(request) {
      calls.push({ method: "LIST", path: request });
      const [path, query = ""] = request.split("?");
      const node = new URLSearchParams(query)
        .get("fieldSelector")
        ?.match(/^spec\.nodeName=(.+)$/)?.[1];
      return [...objects.entries()]
        .filter(([key]) => key.slice(0, key.lastIndexOf("/")) === path)
        .map(([, item]) => clone(item))
        .filter(
          (item) =>
            node === undefined ||
            (item.spec as { nodeName?: string } | undefined)?.nodeName === node,
        );
    },
    async create(path, body) {
      calls.push({ method: "POST", path });
      const item = clone(body) as Item;
      const key = `${path}/${item.metadata.name as string}`;
      if (objects.has(key))
        throw new KubernetesError(409, `Kubernetes POST ${key} returned 409`);
      item.metadata = {
        ...item.metadata,
        uid: randomUUID(),
        generation: 1,
        creationTimestamp: new Date().toISOString(),
      };
      return store(key, item);
    },
    async mergePatch(path, patch) {
      calls.push({ method: "PATCH", path });
      const status = path.endsWith("/status");
      const key = path.replace(/\/status$/, "");
      const current = objects.get(key);
      if (!current) throw missing(key);
      const body = clone(patch) as Record<string, unknown>;
      const precondition = (body.metadata as Item["metadata"] | undefined)
        ?.resourceVersion;
      if (
        precondition !== undefined &&
        precondition !== current.metadata.resourceVersion
      )
        throw new KubernetesError(409, `Kubernetes PATCH ${key} returned 409`);
      if (status) {
        return store(key, {
          ...current,
          status: merge(current.status, body.status),
        });
      }
      delete body.status;
      const next = merge(current, body) as Item;
      if (JSON.stringify(next.spec) !== JSON.stringify(current.spec))
        next.metadata.generation = (current.metadata.generation as number) + 1;
      return store(key, next);
    },
    async replace(path, body) {
      calls.push({ method: "PUT", path });
      const current = objects.get(path);
      if (!current) throw missing(path);
      const item = clone(body) as Item;
      if (item.metadata.resourceVersion !== current.metadata.resourceVersion)
        throw new KubernetesError(409, `Kubernetes PUT ${path} returned 409`);
      item.metadata.uid = current.metadata.uid;
      return store(path, item);
    },
  };

  return {
    api,
    calls,
    objects,
    seed: (collection: string, item: Item) =>
      store(`${collection}/${item.metadata.name as string}`, {
        ...clone(item),
        metadata: {
          uid: randomUUID(),
          generation: 1,
          creationTimestamp: new Date().toISOString(),
          ...clone(item.metadata),
        },
      }),
    // Deletion as the API server does it: immediate without finalizers,
    // otherwise only marked until they are removed.
    delete: (path: string) => {
      const item = objects.get(path);
      if (!item) return;
      if (!(item.metadata.finalizers as string[] | undefined)?.length)
        return objects.delete(path);
      item.metadata.deletionTimestamp ??= new Date().toISOString();
      item.metadata.resourceVersion = String(++version);
    },
    read: (path: string) => {
      const item = objects.get(path);
      return item && clone(item);
    },
    remove: (path: string) => objects.delete(path),
  };
};
